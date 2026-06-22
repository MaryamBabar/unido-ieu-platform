"""
One-time setup: create your admin account and the 6 user accounts.

Run this ONCE after installing dependencies:
  cd eio-rag
  python scripts/setup_users.py

This creates data/users.yaml with bcrypt-hashed passwords.
After running, share each user's username + temporary password securely
(e.g. via encrypted email or WhatsApp). Users cannot change their own
passwords in Version 1 — only the admin can reset them via the Admin tab.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from auth import create_user, list_users

print("\n" + "=" * 60)
print("UNIDO IEU Platform — First-Time User Setup")
print("=" * 60)

existing = list_users()
if existing:
    print(f"\n✓ Users already exist ({len(existing)} found):")
    for u in existing:
        print(f"   • {u['display_name']} (@{u['username']}) — {u['role']}")
    print("\nTo add more users, use the Admin tab in the Streamlit app.")
    print("To reset a password, use the Admin tab.")
    sys.exit(0)

print("""
No users found. Let's create your accounts.

You will be asked to set up:
  1. Your admin account (Maryam — full access)
  2. Up to 6 analyst user accounts

Press Ctrl+C at any time to stop.
""")

users_to_create = [
    {
        "username": "maryam.babar",
        "display_name": "Maryam Babar",
        "role": "admin",
        "description": "Admin (you)",
    },
    # Add your 6 users below — fill in real names and usernames
    # The passwords set here are temporary — users cannot change them themselves
    # You can reset any password from the Admin tab later
    {
        "username": "user2",
        "display_name": "User Two",
        "role": "user",
        "description": "Analyst",
    },
    {
        "username": "user3",
        "display_name": "User Three",
        "role": "user",
        "description": "Analyst",
    },
    {
        "username": "user4",
        "display_name": "User Four",
        "role": "user",
        "description": "Analyst",
    },
    {
        "username": "user5",
        "display_name": "User Five",
        "role": "user",
        "description": "Analyst",
    },
    {
        "username": "user6",
        "display_name": "User Six",
        "role": "user",
        "description": "Analyst",
    },
]

print("=" * 60)
print("NOTE: Edit this script before running to set real names,")
print("usernames, and passwords for your 6 team members.")
print("=" * 60)

created = []
for user_def in users_to_create:
    print(f"\n[{user_def['description']}] {user_def['display_name']} (@{user_def['username']})")
    password = input(f"  Set password (min 8 chars): ").strip()

    if len(password) < 8:
        print("  ⚠️  Password too short — skipping this user.")
        continue

    try:
        create_user(
            username=user_def["username"],
            plain_password=password,
            display_name=user_def["display_name"],
            role=user_def["role"],
            created_by="setup_script",
        )
        print(f"  ✅ Created: @{user_def['username']}")
        created.append({"username": user_def["username"], "display_name": user_def["display_name"]})
    except ValueError as e:
        print(f"  ❌ Error: {e}")

print("\n" + "=" * 60)
print(f"Setup complete. {len(created)} user(s) created:")
for u in created:
    print(f"  • {u['display_name']} (@{u['username']})")
print("\nUsers file: data/users.yaml")
print("Share usernames + temporary passwords with your team via a secure channel.")
print("\nTo manage users later: use the Admin tab in the Streamlit app.")
print("=" * 60)
