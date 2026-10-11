from app.models import Role
from tests.helpers import auth_headers, create_child, create_family, create_migration, make_user


def _setup(client, db):
    make_user(db, "owner@example.com")
    make_user(db, "other@example.com")
    owner = auth_headers(client, "owner@example.com")
    other = auth_headers(client, "other@example.com")
    fam = create_family(client, owner)
    child = create_child(client, owner, fam["id"])
    mig = create_migration(client, owner, fam["id"])
    return owner, other, fam, child, mig


def test_other_citizen_cannot_read_family_data(client, db):
    owner, other, fam, child, mig = _setup(client, db)
    f = f"/api/v1/families/{fam['id']}"
    for url in (f, f"{f}/children", f"{f}/migrations", f"{f}/access",
                f"/api/v1/children/{child['id']}", f"/api/v1/migrations/{mig['id']}"):
        assert client.get(url, headers=other).status_code == 404, url
        assert client.get(url, headers=owner).status_code == 200, url
    assert client.get("/api/v1/families", headers=other).json() == []


def test_other_citizen_cannot_write_family_data(client, db):
    owner, other, fam, child, mig = _setup(client, db)
    f = f"/api/v1/families/{fam['id']}"
    c = f"/api/v1/children/{child['id']}"
    m = f"/api/v1/migrations/{mig['id']}"
    assert client.patch(f, headers=other, json={"household_name": "Hacked"}).status_code == 404
    assert client.post(f"{f}/children", headers=other,
                       json={"full_name": "X", "approx_age_years": 5}).status_code == 404
    assert client.patch(c, headers=other, json={"full_name": "Hacked"}).status_code == 404
    assert client.delete(c, headers=other).status_code == 404
    assert client.post(f"{f}/migrations", headers=other, json={
        "origin_district": "A", "origin_state": "B",
        "destination_district": "C", "destination_state": "D"}).status_code == 404
    assert client.patch(m, headers=other, json={"notes": "Hacked"}).status_code == 404
    assert client.post(f"{m}/status", headers=other, json={"status": "CANCELLED"}).status_code == 404
    assert client.get(f, headers=owner).json()["household_name"] == "Pawar Family"
    assert client.get(m, headers=owner).json()["status"] == "PLANNED"


def test_non_family_roles_are_forbidden(client, db):
    owner, other, fam, child, mig = _setup(client, db)
    for i, role in enumerate([Role.ADMIN, Role.GOVERNMENT, Role.SCHOOL, Role.HEALTHCARE]):
        email = f"role{i}@example.com"
        make_user(db, email, role)
        h = auth_headers(client, email)
        assert client.get("/api/v1/families", headers=h).status_code == 403
        assert client.get(f"/api/v1/families/{fam['id']}", headers=h).status_code == 403
        assert client.get(f"/api/v1/children/{child['id']}", headers=h).status_code == 403
        assert client.get(f"/api/v1/migrations/{mig['id']}", headers=h).status_code == 403


def test_support_worker_sees_only_shared_family_read_only(client, db):
    owner, other, fam, child, mig = _setup(client, db)
    make_user(db, "ngo@example.com", Role.NGO)
    ngo = auth_headers(client, "ngo@example.com")
    f = f"/api/v1/families/{fam['id']}"

    assert client.get(f, headers=ngo).status_code == 404  # not shared yet

    r = client.post(f"{f}/access", headers=owner, json={"email": "ngo@example.com"})
    assert r.status_code == 201
    access_id = r.json()["id"]
    assert len(client.get(f"{f}/access", headers=owner).json()) == 2  # owner + support worker

    assert client.get(f, headers=ngo).status_code == 200
    assert len(client.get(f"{f}/children", headers=ngo).json()) == 1
    assert client.get(f"/api/v1/migrations/{mig['id']}", headers=ngo).status_code == 200
    assert client.patch(f"/api/v1/children/{child['id']}", headers=ngo,
                        json={"education_status": "ENROLLED"}).status_code == 403
    assert client.get(f"{f}/access", headers=ngo).status_code == 403

    assert client.delete(f"{f}/access/{access_id}", headers=owner).status_code == 204
    assert client.get(f, headers=ngo).status_code == 404  # revoked

    assert client.post(f"{f}/access", headers=owner, json={"email": "ngo@example.com"}).status_code == 201
    assert client.get(f, headers=ngo).status_code == 200  # re-granted


def test_grant_access_validation(client, db):
    owner, other, fam, child, mig = _setup(client, db)
    make_user(db, "ngo2@example.com", Role.NGO)
    f = f"/api/v1/families/{fam['id']}"
    # a citizen email is not a support worker
    assert client.post(f"{f}/access", headers=owner, json={"email": "other@example.com"}).status_code == 404
    # someone outside the family cannot grant access to it
    assert client.post(f"{f}/access", headers=other, json={"email": "ngo2@example.com"}).status_code == 404