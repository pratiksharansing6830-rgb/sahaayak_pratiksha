import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import engine
from app.models import (
    Child, Family, Role, ServiceCategory, ServiceNeed, User,
)


def test_duplicate_need_is_blocked_by_database():
    conn = engine.connect()
    trans = conn.begin()
    db = Session(bind=conn)
    try:
        user = User(email="t@example.com", password_hash="x", full_name="T", role=Role.CITIZEN)
        db.add(user)
        db.flush()
        fam = Family(household_name="Test", primary_caregiver_name="T", created_by_user_id=user.id)
        db.add(fam)
        db.flush()
        child = Child(family_id=fam.id, full_name="C")
        db.add(child)
        db.flush()

        db.add(ServiceNeed(child_id=child.id, category=ServiceCategory.EDUCATION, need_description="a"))
        db.flush()

        db.add(ServiceNeed(child_id=child.id, category=ServiceCategory.EDUCATION, need_description="b"))
        with pytest.raises(IntegrityError):
            db.flush()
    finally:
        db.close()
        if trans.is_active:
            trans.rollback()
        conn.close()