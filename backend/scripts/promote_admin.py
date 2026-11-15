#!/usr/bin/env python3
"""
One-off script to promote legitimate admin accounts by email.
Usage:
    python scripts/promote_admin.py admin@example.com
"""
import sys
import os

# Add backend directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.auth.models import DBManager


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/promote_admin.py <user_email>")
        sys.exit(1)

    email = sys.argv[1].strip()
    user = DBManager.get_user_by_email(email)
    if not user:
        print(f"❌ User with email '{email}' not found.")
        sys.exit(1)

    success = DBManager.promote_user_to_admin(email)
    if success:
        print(f"✅ User '{email}' (ID: {user['id']}) has been successfully promoted to admin.")
    else:
        print(f"❌ Failed to promote user '{email}'.")
        sys.exit(1)


if __name__ == "__main__":
    main()
