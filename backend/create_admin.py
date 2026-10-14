"""
Create (or reset) an admin account. Admins cannot sign up through the website.

    python create_admin.py --username admin --name "Raj Patil"
    python create_admin.py --username admin --password "my-strong-password"

Without --password a random one is generated and printed once.
"""

import argparse
from datetime import datetime, timezone

from core import db
from core.security import hash_password, temporary_password


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--name", default="Administrator")
    parser.add_argument("--password", help="at least 8 characters; generated if omitted")
    args = parser.parse_args()

    username = args.username.strip().lower()
    password = args.password or temporary_password()
    if len(password) < 8:
        raise SystemExit("Password must be at least 8 characters")

    existed = db.users.find_one({"_id": username}) is not None
    db.users.update_one(
        {"_id": username},
        {"$set": {"name": args.name, "role": "admin", "status": "active", "language": "en",
                  "password_hash": hash_password(password)},
         "$setOnInsert": {"created_at": datetime.now(timezone.utc), "phone": "", "village": ""}},
        upsert=True,
    )
    print(f"Admin '{username}' {'updated' if existed else 'created'}.")
    if not args.password:
        print(f"Password: {password}   (shown once - change it after logging in)")


if __name__ == "__main__":
    main()
