import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.models import Role, ServiceCategory
from tests.helpers import auth_headers, journey, make_listing, make_provider, make_user

API = "/api/v1"
EDU = ServiceCategory.EDUCATION


def test_production_refuses_a_weak_secret():
    base = dict(environment="production", database_url="postgresql+psycopg://x")
    with pytest.raises(ValidationError):
        Settings(secret_key="CHANGE_ME_generate_a_long_random_string", **base)
    with pytest.raises(ValidationError):
        Settings(secret_key="short", **base)
    assert Settings(secret_key="x" * 40, **base).is_production


def test_security_headers_are_set(client):
    r = client.get(f"{API}/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_district_list_needs_login(client, db):
    assert client.get(f"{API}/services/districts").status_code == 401
    make_user(db, "d@example.com")
    r = client.get(f"{API}/services/districts", headers=auth_headers(client, "d@example.com"))
    assert r.status_code == 200
    assert any(d["name"] == "Pune" and d["latitude"] for d in r.json())


def test_government_report_views_are_audited(client, db):
    make_user(db, "gov-a@example.com", Role.GOVERNMENT)
    make_user(db, "adm-a@example.com", Role.ADMIN)
    g = auth_headers(client, "gov-a@example.com")
    assert client.get(f"{API}/gov/overview", headers=g).status_code == 200
    a = auth_headers(client, "adm-a@example.com")
    events = client.get(f"{API}/admin/audit-events?action=GOV_REPORT_VIEWED", headers=a).json()
    assert len(events) == 1 and events[0]["to_value"] == "overview" and events[0]["actor_role"] == "GOVERNMENT"


def test_admin_platform_health_is_counts_only(client, db):
    make_user(db, "adm-h@example.com", Role.ADMIN)
    make_user(db, "cit-h@example.com")
    a = auth_headers(client, "adm-h@example.com")
    body = client.get(f"{API}/admin/health", headers=a).json()
    assert body["database"] == "connected" and body["users_by_role"]["ADMIN"] >= 1
    assert "cit-h@example.com" not in str(body)
    assert client.get(f"{API}/admin/health", headers=auth_headers(client, "cit-h@example.com")).status_code == 403


def test_referral_must_be_in_the_destination_district(client, db):
    h, fam, child, mig, needs = journey(client, db)
    far = make_listing(db, "Nagpur School", EDU, "Nagpur")
    r = client.post(f"{API}/needs/{needs['EDUCATION']['id']}/referrals", headers=h,
                    json={"service_listing_id": str(far.id)})
    assert r.status_code == 422 and "destination" in r.json()["detail"].lower()


def test_destination_change_withdraws_active_referrals(client, db):
    h, fam, child, mig, needs = journey(client, db)
    org, user, listing = make_provider(db)
    sh = auth_headers(client, user.email)
    edu = needs["EDUCATION"]["id"]
    ref = client.post(f"{API}/needs/{edu}/referrals", headers=h,
                      json={"service_listing_id": str(listing.id)}).json()
    r = client.patch(f"{API}/migrations/{mig['id']}", headers=h, json={"destination_district": "Nagpur"})
    assert r.status_code == 200
    assert client.get(f"{API}/needs/{edu}", headers=h).json()["status"] == "PENDING"
    assert client.get(f"{API}/needs/{edu}/referrals", headers=h).json()[0]["status"] == "WITHDRAWN"
    r = client.post(f"{API}/provider/referrals/{ref['id']}/respond", headers=sh,
                    json={"response_type": "ACCEPTED"})
    assert r.status_code == 409