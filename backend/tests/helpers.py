from datetime import date, timedelta

from app.core.security import hash_password
from app.models import Role, User

PASSWORD = "Passw0rd!test"


def make_user(db, email, role=Role.CITIZEN, organization_id=None):
    user = User(
        email=email, password_hash=hash_password(PASSWORD), full_name="Test User",
        role=role, organization_id=organization_id,
    )
    db.add(user)
    db.flush()
    return user


def auth_headers(client, email, password=PASSWORD):
    r = client.post("/api/v1/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def create_family(client, headers, name="Pawar Family"):
    r = client.post("/api/v1/families", headers=headers, json={
        "household_name": name, "primary_caregiver_name": "Sunita Pawar",
        "origin_district": "Beed", "origin_state": "Maharashtra", "consent_given": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


def create_child(client, headers, family_id, name="Asha", age=8):
    r = client.post(f"/api/v1/families/{family_id}/children", headers=headers,
                    json={"full_name": name, "approx_age_years": age})
    assert r.status_code == 201, r.text
    return r.json()


def create_migration(client, headers, family_id, **overrides):
    body = {
        "origin_district": "Beed", "origin_state": "Maharashtra",
        "destination_district": "Pune", "destination_state": "Maharashtra",
        "planned_date": (date.today() + timedelta(days=30)).isoformat(),
    }
    body.update(overrides)
    r = client.post(f"/api/v1/families/{family_id}/migrations", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()
def assess(client, headers, migration_id):
    r = client.post(f"/api/v1/migrations/{migration_id}/assess", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def journey(client, db, email="family@example.com", education="NOT_ENROLLED", do_assess=True):
    """Citizen + family + one child + one planned migration (+ assessment).
    Returns (headers, family, child, migration, {category: need})."""
    make_user(db, email)
    h = auth_headers(client, email)
    fam = create_family(client, h)
    child = create_child(client, h, fam["id"])
    if education:
        r = client.patch(f"/api/v1/children/{child['id']}", headers=h, json={"education_status": education})
        assert r.status_code == 200, r.text
    mig = create_migration(client, h, fam["id"])
    needs = {}
    if do_assess:
        needs = {n["category"]: n for n in assess(client, h, mig["id"])["needs"]}
    return h, fam, child, mig, needs