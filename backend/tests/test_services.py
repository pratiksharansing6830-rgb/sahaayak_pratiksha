import uuid

from sqlalchemy import select

from app.models import AuditEvent, Role, ServiceCategory, VerificationStatus
from tests.helpers import auth_headers, make_listing, make_user

API = "/api/v1"


def _citizen(client, db, email="svc@example.com"):
    make_user(db, email)
    return auth_headers(client, email)


def _admin(client, db, email="svc-admin@example.com"):
    make_user(db, email, Role.ADMIN)
    return auth_headers(client, email)


def test_search_requires_login(client):
    assert client.get(f"{API}/services?district=Pune").status_code == 401


def test_unrecognised_district_is_not_defaulted(client, db):
    h = _citizen(client, db)
    make_listing(db, district="Pune")
    r = client.get(f"{API}/services?district=Zzzzz", headers=h)
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["code"] == "LOCATION_NOT_RECOGNISED" and d["suggestions"] == []
    r = client.get(f"{API}/services?district=Punee", headers=h)
    assert r.status_code == 422 and "Pune" in r.json()["detail"]["suggestions"]


def test_ambiguous_and_unsupported_locations(client, db):
    h = _citizen(client, db)
    r = client.get(f"{API}/services?district=Mumbai", headers=h)
    assert r.status_code == 422
    assert {"Mumbai City", "Mumbai Suburban"} <= set(r.json()["detail"]["suggestions"])
    r = client.get(f"{API}/services?district=Pune&state=Karnataka", headers=h)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "STATE_NOT_SUPPORTED"


def test_old_district_names_resolve(client, db):
    h = _citizen(client, db)
    r = client.get(f"{API}/services?district=Aurangabad", headers=h)
    assert r.status_code == 200
    assert r.json()["location"]["district"] == "Chhatrapati Sambhajinagar"


def test_search_filters_and_labels(client, db):
    h = _citizen(client, db)
    make_listing(db, "Verified School", ServiceCategory.EDUCATION, "Pune", latitude=18.53,
                 longitude=73.85, verification_status=VerificationStatus.VERIFIED,
                 data_source="District office list")
    make_listing(db, "Sample Clinic", ServiceCategory.HEALTHCARE, "Pune",
                 verification_status=VerificationStatus.SAMPLE)
    make_listing(db, "Nagpur School", ServiceCategory.EDUCATION, "Nagpur")
    gone = make_listing(db, "Closed School", ServiceCategory.EDUCATION, "Pune")
    gone.is_active = False
    db.flush()

    body = client.get(f"{API}/services?district=pune", headers=h).json()
    assert body["location"]["district"] == "Pune" and body["location"]["approximate"] is True
    assert [s["name"] for s in body["results"]] == ["Verified School", "Sample Clinic"]
    by = {s["name"]: s for s in body["results"]}
    assert 0 <= by["Verified School"]["distance_km_approx"] < 5
    assert by["Sample Clinic"]["distance_km_approx"] is None  # no coordinates, no distance
    assert by["Sample Clinic"]["is_sample"] is True and by["Verified School"]["is_verified"] is True
    assert "does not confirm" in by["Verified School"]["availability_note"].lower()

    r = client.get(f"{API}/services?district=Pune&category=HEALTHCARE", headers=h).json()
    assert [s["name"] for s in r["results"]] == ["Sample Clinic"]
    r = client.get(f"{API}/services?district=Pune&include_sample=false", headers=h).json()
    assert [s["name"] for s in r["results"]] == ["Verified School"]


def test_admin_creates_listing_with_canonical_district(client, db):
    h = _admin(client, db)
    r = client.post(f"{API}/admin/services", headers=h, json={
        "name": "Gov School", "category": "EDUCATION", "district": "pune"})
    assert r.status_code == 201
    b = r.json()
    assert b["district"] == "Pune" and b["state"] == "Maharashtra"
    assert b["verification_status"] == "UNVERIFIED" and b["last_verified_at"] is None


def test_listing_rules(client, db):
    h = _admin(client, db)
    base = {"name": "X", "category": "EDUCATION", "district": "Pune"}
    url = f"{API}/admin/services"
    assert client.post(url, headers=h, json={**base, "verification_status": "VERIFIED"}).status_code == 422
    ok = client.post(url, headers=h, json={
        **base, "verification_status": "VERIFIED", "data_source": "Block office register"})
    assert ok.status_code == 201 and ok.json()["last_verified_at"] is not None
    assert client.post(url, headers=h, json={**base, "latitude": 18.5}).status_code == 422
    assert client.post(url, headers=h, json={**base, "district": "Atlantis"}).status_code == 422


def test_only_admin_manages_listings(client, db):
    c = _citizen(client, db)
    assert client.post(f"{API}/admin/services", headers=c, json={
        "name": "X", "category": "EDUCATION", "district": "Pune"}).status_code == 403
    assert client.get(f"{API}/admin/services", headers=c).status_code == 403


def test_admin_verifies_and_deactivates_with_audit(client, db):
    a = _admin(client, db)
    c = _citizen(client, db)
    s = client.post(f"{API}/admin/services", headers=a, json={
        "name": "Gov School", "category": "EDUCATION", "district": "Pune"}).json()
    r = client.patch(f"{API}/admin/services/{s['id']}", headers=a, json={
        "verification_status": "VERIFIED", "data_source": "Visited by block officer"})
    assert r.status_code == 200 and r.json()["last_verified_at"] is not None
    events = db.scalars(select(AuditEvent).where(
        AuditEvent.action == "SERVICE_VERIFICATION_CHANGED",
        AuditEvent.entity_id == uuid.UUID(s["id"]))).all()
    assert [(e.from_value, e.to_value) for e in events] == [("UNVERIFIED", "VERIFIED")]

    assert len(client.get(f"{API}/services?district=Pune", headers=c).json()["results"]) == 1
    assert client.delete(f"{API}/admin/services/{s['id']}", headers=a).status_code == 204
    assert client.get(f"{API}/services?district=Pune", headers=c).json()["results"] == []
    assert client.get(f"{API}/services/{s['id']}", headers=c).status_code == 404