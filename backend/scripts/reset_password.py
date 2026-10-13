"""Reset a user's password. Run from backend/:  python -m scripts.reset_password"""
import getpass

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User
from app.services.audit import log_event


def main() -> None:
    email = input("User email: ").strip().lower()
    password = getpass.getpass("New password (8-72 chars): ")
    confirm = getpass.getpass("Confirm new password: ")

    if password != confirm:
        raise SystemExit("Passwords do not match.")
    if not 8 <= len(password) <= 72:
        raise SystemExit("Password must be 8 to 72 characters.")

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            raise SystemExit("No user with that email.")
        user.password_hash = hash_password(password)
        log_event(db, actor=user, action="PASSWORD_RESET_BY_SCRIPT", entity_type="user", entity_id=user.id)
        db.commit()
    print("Password updated.")


if __name__ == "__main__":
    main()