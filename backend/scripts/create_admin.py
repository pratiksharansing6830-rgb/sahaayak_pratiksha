"""Create the first administrator. Run from backend/:  python -m scripts.create_admin"""
import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Role, User
from app.services.audit import log_event


def main() -> None:
    email = input("Admin email: ").strip().lower()
    full_name = input("Full name: ").strip()
    password = getpass.getpass("Password (8-72 chars): ")
    confirm = getpass.getpass("Confirm password: ")

    if not email or not full_name:
        raise SystemExit("Email and name are required.")
    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if not 8 <= len(password) <= 72:
        raise SystemExit("Password must be 8 to 72 characters.")

    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            raise SystemExit("A user with this email already exists.")
        user = User(
            email=email, password_hash=hash_password(password),
            full_name=full_name, role=Role.ADMIN,
        )
        db.add(user)
        db.flush()
        log_event(db, actor=user, action="ADMIN_BOOTSTRAPPED", entity_type="user", entity_id=user.id)
        db.commit()
    print("Admin created.")


if __name__ == "__main__":
    main()