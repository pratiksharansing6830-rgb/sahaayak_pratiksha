from app.models import Role
from tests.helpers import PASSWORD, auth_headers, make_user


def test_citizen_cannot_use_admin_endpoints(client, db):
    make_user(db, "citizen@example.com", Role.CITIZEN)
    h = auth_headers(client, "citizen@example.com")
    assert client.get("/api/v1/admin/users", headers=h).status_code == 403
    assert client.get("/api/v1/admin/audit-events", headers=h).status_code == 403
    assert client.post("/api/v1/admin/organizations", headers=h, json={
        "name": "X", "org_type": "SCHOOL"}).status_code == 403


def test_admin_creates_school_user_who_is_not_admin(client, db):
    make_user(db, "admin-t@example.com", Role.ADMIN)
    admin_h = auth_headers(client, "admin-t@example.com")

    org = client.post("/api/v1/admin/organizations", headers=admin_h, json={
        "name": "Test School", "org_type": "SCHOOL", "district": "Pune", "state": "Maharashtra",
    })
    assert org.status_code == 201

    r = client.post("/api/v1/admin/users", headers=admin_h, json={
        "email": "school-t@example.com", "password": PASSWORD, "full_name": "Head Teacher",
        "role": "SCHOOL", "organization_id": org.json()["id"],
    })
    assert r.status_code == 201 and r.json()["role"] == "SCHOOL"

    school_h = auth_headers(client, "school-t@example.com")
    assert client.get("/api/v1/admin/users", headers=school_h).status_code == 403


def test_provider_role_requires_organization(client, db):
    make_user(db, "admin-t2@example.com", Role.ADMIN)
    h = auth_headers(client, "admin-t2@example.com")
    r = client.post("/api/v1/admin/users", headers=h, json={
        "email": "noorg@example.com", "password": PASSWORD, "full_name": "N", "role": "HEALTHCARE",
    })
    assert r.status_code == 422


def test_admin_cannot_deactivate_self(client, db):
    admin = make_user(db, "admin-t3@example.com", Role.ADMIN)
    h = auth_headers(client, "admin-t3@example.com")
    r = client.patch(f"/api/v1/admin/users/{admin.id}", headers=h, json={"is_active": False})
    assert r.status_code == 400


def test_role_change_is_audited_and_visible(client, db):
    make_user(db, "admin-t4@example.com", Role.ADMIN)
    target = make_user(db, "target@example.com", Role.CITIZEN)
    h = auth_headers(client, "admin-t4@example.com")

    r = client.patch(f"/api/v1/admin/users/{target.id}", headers=h, json={"role": "NGO"})
    assert r.status_code == 200 and r.json()["role"] == "NGO"

    events = client.get("/api/v1/admin/audit-events?action=USER_ROLE_CHANGED", headers=h).json()
    assert any(e["from_value"] == "CITIZEN" and e["to_value"] == "NGO" for e in events)