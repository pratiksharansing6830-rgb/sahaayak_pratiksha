import json

from app.core.config import settings
from tests.helpers import auth_headers, journey, make_provider

API = "/api/v1"
ENDPOINTS = ["overview", "unresolved-by-category", "destinations", "trends",
             "service-gaps", "priority", "alerts"]


def test_full_demo_scenario(client, db, monkeypatch):
    monkeypatch.setattr(settings, "min_group_size", 1)  # one family only, for the demo
    # 1-3. A family plans a move; the unresolved education need is identified.
    h, fam, child, mig, needs = journey(client, db, email="demo-family@example.com")
    edu = needs["EDUCATION"]["id"]
    assert needs["EDUCATION"]["status"] == "PENDING" and needs["EDUCATION"]["is_open"]

    # 4. They discover a potential destination school (a listing, not yet a referral).
    org, user, listing = make_provider(db)
    sh = auth_headers(client, user.email)
    found = client.get(f"{API}/services?district=Pune", headers=h).json()
    assert [s["id"] for s in found["results"]] == [str(listing.id)]
    assert client.get(f"{API}/needs/{edu}/referrals", headers=h).json() == []

    # 5. A referral is recorded: the need is referred, never confirmed.
    ref = client.post(f"{API}/needs/{edu}/referrals", headers=h,
                      json={"service_listing_id": str(listing.id)}).json()
    assert client.get(f"{API}/needs/{edu}", headers=h).json()["status"] == "REFERRED"

    # 6-7. The provider asks for more information; the need stays open with a follow-up.
    r = client.post(f"{API}/provider/referrals/{ref['id']}/respond", headers=sh, json={
        "response_type": "INFO_REQUESTED", "message": "Please send the transfer certificate"})
    assert r.status_code == 200
    d = client.get(f"{API}/needs/{edu}", headers=h).json()
    assert d["status"] == "FOLLOW_UP_REQUIRED" and d["is_open"]
    assert any(f["status"] == "OPEN" for f in d["follow_ups"])

    # The family answers; the provider accepts, then confirms the outcome separately.
    assert client.post(f"{API}/needs/{edu}/contact-attempts", headers=h, json={
        "referral_id": ref["id"], "method": "MESSAGE", "result": "OTHER",
        "note": "Certificate sent"}).status_code == 201
    assert client.post(f"{API}/provider/referrals/{ref['id']}/respond", headers=sh,
                       json={"response_type": "ACCEPTED"}).status_code == 200
    assert client.get(f"{API}/needs/{edu}", headers=h).json()["is_open"] is True
    assert client.post(f"{API}/provider/referrals/{ref['id']}/confirm-outcome", headers=sh,
                       json={"outcome": "Admitted to Class 3"}).status_code == 200

    # 8-9. The family sees the confirmed outcome and its history.
    d = client.get(f"{API}/needs/{edu}", headers=h).json()
    assert d["status"] == "SUPPORT_CONFIRMED" and d["confirmations"][0]["provider_verified"] is True
    assert len(d["history"]) >= 4

    # Other needs are still open: nothing else was confirmed by this.
    s = client.get(f"{API}/families/{fam['id']}/continuity-summary", headers=h).json()
    assert s["totals"]["open"] == 5 and s["totals"]["support_confirmed_by_provider"] == 1

    # 10. Government sees aggregates only.
    make_gov = __import__("tests.helpers", fromlist=["make_user"]).make_user
    make_gov(db, "demo-gov@example.com", __import__("app.models", fromlist=["Role"]).Role.GOVERNMENT)
    g = auth_headers(client, "demo-gov@example.com")
    o = client.get(f"{API}/gov/overview", headers=g).json()
    assert o["children_support_confirmed_by_provider"] == 1
    cats = [r["category"] for r in client.get(f"{API}/gov/unresolved-by-category", headers=g).json()["rows"]]
    assert "EDUCATION" not in cats and len(cats) == 5
    blob = json.dumps([client.get(f"{API}/gov/{e}", headers=g).json() for e in ENDPOINTS])
    for private in ("Asha", "Sunita", "Pawar", "Beed", "demo-family", str(fam["id"]), str(child["id"])):
        assert private not in blob, private