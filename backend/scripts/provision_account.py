"""Command-line utility to provision administrative and officer accounts securely."""
import sys
import os
import argparse
from pathlib import Path

# Setup paths
sys.path.insert(0, str(Path(__file__).parent.parent))
os.chdir(str(Path(__file__).parent.parent))

from app.database import SessionLocal
from app.models import User
from app.auth import hash_password
from app.services.audit import record_event


def provision_account(officer_id: str, name: str, email: str, password: str, role: str):
    db = SessionLocal()
    try:
        # Check uniqueness
        if db.query(User).filter(User.email == email).first():
            print(f"Error: Account with email '{email}' already exists.")
            return False
        if db.query(User).filter(User.officer_id == officer_id).first():
            print(f"Error: Account with officer ID '{officer_id}' already exists.")
            return False

        user = User(
            officer_id=officer_id,
            name=name,
            email=email,
            password_hash=hash_password(password),
            role=role,
            active=True,
        )
        db.add(user)
        db.flush()

        record_event(
            db,
            "OFFICER_PROVISIONED_CLI",
            actor_id="CLI_BOOTSTRAP",
            object_type="user",
            object_id=user.id,
            payload={"officer_id": officer_id, "role": role, "email": email},
        )
        db.commit()
        print(f"Success: Account '{officer_id}' ({name}, role={role}) provisioned successfully.")
        return True
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Provision officer or administrator account for AICTE Verification Engine.")
    parser.add_argument("--id", required=True, help="Unique Officer ID (e.g. AICTE-OFF-01)")
    parser.add_argument("--name", required=True, help="Full display name")
    parser.add_argument("--email", required=True, help="Official email address")
    parser.add_argument("--password", required=True, help="Account password (min 8 chars)")
    parser.add_argument(
        "--role",
        default="SCRUTINY_OFFICER",
        choices=["SCRUTINY_OFFICER", "SUPERVISOR", "SENIOR_REVIEWER", "SYSTEM_ADMIN", "AUDITOR"],
        help="Assigned role",
    )

    args = parser.parse_args()

    if len(args.password) < 8:
        print("Error: Password must be at least 8 characters long.")
        sys.exit(1)

    success = provision_account(args.id, args.name, args.email, args.password, args.role)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

