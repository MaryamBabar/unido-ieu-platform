"""
User authentication and access control for the UNIDO IEU platform.

Design:
  - Users stored in data/users.yaml (bcrypt-hashed passwords)
  - Admin (Maryam) manages users via the Streamlit admin tab OR by editing the YAML
  - Session tokens are random UUIDs passed between Streamlit and FastAPI
  - Sessions stored in-memory on the backend (cleared on restart)
  - No JWT, no database — simple, auditable, maintainable by one developer

Security properties:
  - Passwords are bcrypt-hashed (never stored in plaintext)
  - Each user gets a unique session token on login
  - Invalid/expired tokens return 401 — no access to any API endpoint
  - Admin can immediately revoke a user by removing them from users.yaml
  - All login attempts logged (success and failure) with timestamp + username
"""

import uuid
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
import yaml

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.parent
USERS_FILE = BASE_DIR / "data" / "users.yaml"


# ─────────────────────────────────────────────────────────────────────────────
# In-memory session store
# (Sessions persist as long as the backend is running — cleared on restart)
# ─────────────────────────────────────────────────────────────────────────────

_active_sessions: dict[str, dict] = {}
# Format: { session_token: { username, role, login_time } }


# ─────────────────────────────────────────────────────────────────────────────
# User store (users.yaml)
# ─────────────────────────────────────────────────────────────────────────────

def _load_users() -> dict:
    """Load users from YAML file. Returns empty dict if file doesn't exist."""
    if not USERS_FILE.exists():
        logger.warning(f"Users file not found: {USERS_FILE}. Run setup to create it.")
        return {}
    with open(USERS_FILE, "r") as f:
        data = yaml.safe_load(f) or {}
    return data.get("users", {})


def _save_users(users: dict) -> None:
    """Save users dict back to YAML file."""
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w") as f:
        yaml.dump({"users": users}, f, default_flow_style=False, allow_unicode=True)


# ─────────────────────────────────────────────────────────────────────────────
# Password utilities
# ─────────────────────────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a plaintext password with bcrypt. Returns the hash string."""
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(plain_password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Authentication
# ─────────────────────────────────────────────────────────────────────────────

def authenticate(username: str, password: str) -> Optional[str]:
    """
    Authenticate a user. Returns a session token on success, None on failure.
    Logs all attempts.
    """
    users = _load_users()
    username = username.strip().lower()

    if username not in users:
        logger.warning(f"AUTH FAILED — unknown user: '{username}'")
        return None

    user = users[username]

    if not user.get("active", True):
        logger.warning(f"AUTH FAILED — deactivated user: '{username}'")
        return None

    if not verify_password(password, user.get("password_hash", "")):
        logger.warning(f"AUTH FAILED — wrong password: '{username}'")
        return None

    # Generate session token
    token = str(uuid.uuid4())
    _active_sessions[token] = {
        "username": username,
        "role": user.get("role", "user"),
        "display_name": user.get("display_name", username),
        "login_time": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"AUTH SUCCESS — user '{username}' logged in (token: {token[:8]}...)")
    return token


def validate_session(token: str) -> Optional[dict]:
    """
    Check if a session token is valid.
    Returns the session dict (username, role, display_name) or None.
    """
    if not token:
        return None
    return _active_sessions.get(token)


def logout(token: str) -> None:
    """Invalidate a session token."""
    session = _active_sessions.pop(token, None)
    if session:
        logger.info(f"LOGOUT — user '{session['username']}' (token: {token[:8]}...)")


def get_active_sessions() -> list[dict]:
    """Return list of active sessions (for admin view)."""
    return [
        {
            "username": s["username"],
            "display_name": s["display_name"],
            "role": s["role"],
            "login_time": s["login_time"],
            "token_prefix": token[:8] + "...",
        }
        for token, s in _active_sessions.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# User management (admin only)
# ─────────────────────────────────────────────────────────────────────────────

def create_user(
    username: str,
    plain_password: str,
    display_name: str,
    role: str = "user",
    created_by: str = "admin",
) -> dict:
    """
    Create a new user. Hashes the password before storing.
    Raises ValueError if username already exists.
    """
    users = _load_users()
    username = username.strip().lower()

    if username in users:
        raise ValueError(f"User '{username}' already exists.")

    if len(plain_password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    users[username] = {
        "display_name": display_name.strip(),
        "password_hash": hash_password(plain_password),
        "role": role,
        "active": True,
        "created_by": created_by,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_users(users)
    logger.info(f"USER CREATED — '{username}' (role: {role}, created by: {created_by})")
    return {"username": username, "display_name": display_name, "role": role}


def set_user_active(username: str, active: bool, changed_by: str = "admin") -> None:
    """Activate or deactivate a user. Deactivated users cannot log in."""
    users = _load_users()
    username = username.strip().lower()

    if username not in users:
        raise ValueError(f"User '{username}' not found.")

    users[username]["active"] = active
    _save_users(users)

    # Revoke active sessions for deactivated users
    if not active:
        tokens_to_remove = [t for t, s in _active_sessions.items() if s["username"] == username]
        for token in tokens_to_remove:
            _active_sessions.pop(token, None)
        logger.info(f"USER DEACTIVATED — '{username}', {len(tokens_to_remove)} session(s) revoked")
    else:
        logger.info(f"USER ACTIVATED — '{username}' (by: {changed_by})")


def change_password(username: str, new_password: str, changed_by: str = "admin") -> None:
    """Change a user's password and revoke all their active sessions."""
    users = _load_users()
    username = username.strip().lower()

    if username not in users:
        raise ValueError(f"User '{username}' not found.")

    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    users[username]["password_hash"] = hash_password(new_password)
    _save_users(users)

    # Force re-login
    tokens_to_remove = [t for t, s in _active_sessions.items() if s["username"] == username]
    for token in tokens_to_remove:
        _active_sessions.pop(token, None)

    logger.info(f"PASSWORD CHANGED — '{username}' (by: {changed_by}), {len(tokens_to_remove)} session(s) revoked")


def delete_user(username: str, deleted_by: str = "admin") -> None:
    """Permanently remove a user."""
    users = _load_users()
    username = username.strip().lower()

    if username not in users:
        raise ValueError(f"User '{username}' not found.")

    del users[username]
    _save_users(users)

    # Revoke sessions
    tokens_to_remove = [t for t, s in _active_sessions.items() if s["username"] == username]
    for token in tokens_to_remove:
        _active_sessions.pop(token, None)

    logger.info(f"USER DELETED — '{username}' (by: {deleted_by})")


def list_users() -> list[dict]:
    """Return all users (without password hashes) for admin display."""
    users = _load_users()
    return [
        {
            "username": uname,
            "display_name": u.get("display_name", uname),
            "role": u.get("role", "user"),
            "active": u.get("active", True),
            "created_at": u.get("created_at", ""),
            "created_by": u.get("created_by", ""),
        }
        for uname, u in users.items()
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Initial setup: create admin user if no users exist
# ─────────────────────────────────────────────────────────────────────────────

def setup_initial_admin(admin_username: str, admin_password: str) -> bool:
    """
    Create the first admin user if no users exist yet.
    Returns True if created, False if users already exist.
    Called once during first-time setup.
    """
    users = _load_users()
    if users:
        return False  # Already initialised

    create_user(
        username=admin_username,
        plain_password=admin_password,
        display_name="Maryam Babar (Admin)",
        role="admin",
        created_by="system",
    )
    logger.info(f"Initial admin created: '{admin_username}'")
    return True
