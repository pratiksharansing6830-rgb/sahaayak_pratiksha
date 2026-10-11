from datetime import date, timedelta

from tests.helpers import auth_headers, create_child, create_family, make_user

FAMILIES = "/api/v1/families"


def _citizen(client, db, email="mother@example.com"):
    make_user(db, email)
    return auth_headers(client, email)


def test_create_family_requires_consent(client, db):
    h = _citizen(client, db)
    r = client.post(FAMILIES, headers=h, json={
        "household_name": "X", "primary_caregiver_name": "Y", "consent_given": False})
    assert r.status_code == 422
    assert client.get(FAMILIES, headers=h).json() == []


def test_create_family_records_consent_and_owner_access(client, db):
    h = _citizen(client, db)
    fam = create_family(client, h)
    assert fam["consent_given_at"] is not None and fam["privacy_notice_version"]
    listed = client.get(FAMILIES, headers=h).json()
    assert [f["id"] for f in listed] == [fam["id"]]


def test_family_rejects_unknown_fields(client, db):
    h = _citizen(client, db)
    r = client.post(FAMILIES, headers=h, json={
        "household_name": "X", "primary_caregiver_name": "Y", "consent_given": True,
        "created_by_user_id": "00000000-0000-0000-0000-000000000000"})
    assert r.status_code == 422
    fam = create_family(client, h)
    r = client.patch(f"{FAMILIES}/{fam['id']}", headers=h, json={"deleted_at": "2026-01-01T00:00:00Z"})
    assert r.status_code == 422


def test_add_and_update_child(client, db):
    h = _citizen(client, db)
    fam = create_family(client, h)
    child = create_child(client, h, fam["id"])
    assert child["education_status"] == "UNKNOWN"
    r = client.patch(f"/api/v1/children/{child['id']}", headers=h, json={
        "education_status": "NOT_ENROLLED", "current_school_name": "ZP School Beed"})
    assert r.status_code == 200 and r.json()["education_status"] == "NOT_ENROLLED"
    assert len(client.get(f"{FAMILIES}/{fam['id']}/children", headers=h).json()) == 1


def test_child_validation(client, db):
    h = _citizen(client, db)
    fam = create_family(client, h)
    url = f"{FAMILIES}/{fam['id']}/children"
    adult = (date.today() - timedelta(days=365 * 20)).isoformat()
    future = (date.today() + timedelta(days=5)).isoformat()
    assert client.post(url, headers=h, json={"full_name": "A", "date_of_birth": adult}).status_code == 422
    assert client.post(url, headers=h, json={"full_name": "A", "date_of_birth": future}).status_code == 422
    assert client.post(url, headers=h, json={"full_name": "A"}).status_code == 422
    assert client.post(url, headers=h, json={"full_name": "A", "approx_age_years": 25}).status_code == 422
    assert client.post(url, headers=h, json={"full_name": "  ", "approx_age_years": 5}).status_code == 422


def test_child_soft_delete(client, db):
    h = _citizen(client, db)
    fam = create_family(client, h)
    child = create_child(client, h, fam["id"])
    assert client.delete(f"/api/v1/children/{child['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/children/{child['id']}", headers=h).status_code == 404
    assert client.get(f"{FAMILIES}/{fam['id']}/children", headers=h).json() == []


def test_required_child_fields_cannot_be_nulled(client, db):
    h = _citizen(client, db)
    fam = create_family(client, h)
    child = create_child(client, h, fam["id"])
    r = client.patch(f"/api/v1/children/{child['id']}", headers=h, json={"full_name": None})
    assert r.status_code == 422