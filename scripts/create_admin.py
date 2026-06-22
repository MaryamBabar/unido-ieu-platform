"""
Quick admin setup — creates only Maryam's admin account.
Run once: python scripts/create_admin.py
Then log in at http://localhost:8501 with username: maryam.babar
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from auth import create_user, list_users

existing = list_users()
if any(u["username"] == "maryam.babar" for u in existing):
    print("✅ Admin account already exists. Log in with username: maryam.babar")
    sys.exit(0)

print("\nCreating your admin account...")
password = input("Choose a password (min 8 characters): ").strip()

if len(password) < 8:
    print("❌ Password must be at least 8 characters.")
    sys.exit(1)

create_user(
    username="maryam.babar",
    plain_password=password,
    display_name="Maryam Babar",
    role="admin",
    created_by="setup",
)

print("\n✅ Admin account created!")
print("   Username: maryam.babar")
print("   Password: (what you just entered)")
print("\nGo to http://localhost:8501 and log in.")
