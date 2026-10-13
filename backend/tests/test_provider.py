import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import AuditEvent, Referral, Role, ServiceCategory
from tests.helpers import auth_headers, journey, make_listing, make_provider, make_user

API = "/api/v1"
P = f"{API}/provider"
EDU = ServiceCategory.EDUCATION
PHONE = "+91 9876543210"


def _setup(client, db):
    """Family with an education need referred to a school that belongs to a provider organisation."""
    h, fam, child, mig, needs = journey(client, db)
    org, user, listing = make_provider(db)
    sh = auth_headers(client, user.email)
    edu = needs["EDUCATION"]["id"]
    r = client.post(f"{API}/needs/{edu}/referrals", headers=h, json={"service_listing_id": str(listing.id)})
    assert r.status_code == 201, r.text
    return h, fam, edu, r.json(), sh, listing


def _respond(client, sh, ref_id, rtype, **extra):
    return client.post(f"{P}/referrals/{ref_id}/respond", headers=sh,
                       json={"response_type": rtype, **extra})


def _confirm(client, sh, ref_id, outcome="Admitted to Class 3", **extra):
    return client.post(f"{P}/referrals/{ref_id}/confirm-outcome", headers=sh,
                       json={"outcome": outcome, **extra})


def _need(client, h, need_id):
    return client.get(f"{API}/needs/{need_id}", headers=h).json()


def _totals(client, h, family_id):
    return client.get(f"{API}/families/{family_id}/continuity-summary", headers=h).json()["totals"]


def test_provider_sees_only_own_referrals_with_minimal_data(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    client.patch(f"{API}/families/{fam['id']}", headers=h, json={"contact_phone": PHONE})
    rows = client.get(f"{P}/referrals", headers=sh).json()
    assert [r["id"] for r in rows] == [ref["id"]]
    r = rows[0]
    assert r["child_name"] == "Asha" and r["category"] == "EDUCATION"
    assert r["destination_district"] == "Pune"
    assert r["family_contact_phone"] is None      # not shared until the referral is accepted
    assert r["accommodations_note"] is None
    assert "household_name" not in r and "primary_caregiver_name" not in r

    _, other, _ = make_provider(db, email="school2@example.com", org_name="Other Org", listing_name="School B")
    oh = auth_headers(client, other.email)
    assert client.get(f"{P}/referrals", headers=oh).json() == []
    assert client.get(f"{P}/referrals/{ref['id']}", headers=oh).status_code == 404
    assert _respond(client, oh, ref["id"], "ACCEPTED").status_code == 404
    assert _confirm(client, oh, ref["id"]).status_code == 404
    assert _need(client, h, edu)["status"] == "REFERRED"


def test_only_provider_roles_with_an_organisation_can_use_provider_api(client, db):
    h = _setup(client, db)[0]
    heads = {"citizen": h}
    for i, role in enumerate([Role.ADMIN, Role.GOVERNMENT]):
        make_user(db, f"x{i}@example.com", role)
        heads[role.value] = auth_headers(client, f"x{i}@example.com")
    make_user(db, "noorg@example.com", Role.SCHOOL)  # provider role, but no organisation
    heads["noorg"] = auth_headers(client, "noorg@example.com")
    for who, hh in heads.items():
        for url in (f"{P}/referrals", f"{P}/dashboard"):
            assert client.get(url, headers=hh).status_code == 403, (who, url)


def test_receipt_updates_need_but_not_referral_decision(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    r = _respond(client, sh, ref["id"], "RECEIVED")
    assert r.status_code == 200 and r.json()["status"] == "RECORDED"
    assert _need(client, h, edu)["status"] == "AWAITING_PROVIDER_RESPONSE"
    assert _respond(client, sh, ref["id"], "RECEIVED").status_code == 409
    seen = client.get(f"{API}/needs/{edu}/referrals", headers=h).json()[0]
    assert [x["response_type"] for x in seen["provider_responses"]] == ["RECEIVED"]


def test_acceptance_is_not_support_received(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    client.patch(f"{API}/families/{fam['id']}", headers=h, json={"contact_phone": PHONE})
    r = _respond(client, sh, ref["id"], "ACCEPTED", message="Please come on Monday")
    assert r.status_code == 200
    assert r.json()["status"] == "ACCEPTED" and r.json()["family_contact_phone"] == PHONE
    d = _need(client, h, edu)
    assert d["status"] == "REFERRED" and d["is_open"] is True and d["confirmations"] == []
    assert "not confirmation" in d["status_explanation"].lower()
    t = _totals(client, h, fam["id"])
    assert t["support_confirmed_by_provider"] == 0 and t["support_confirmed_by_family"] == 0
    events = db.scalars(select(AuditEvent).where(
        AuditEvent.entity_id == uuid.UUID(ref["id"]), AuditEvent.action == "PROVIDER_RESPONDED")).all()
    assert [(e.from_value, e.to_value) for e in events] == [("RECORDED", "ACCEPTED")]


def test_information_request_and_reply_flow(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    assert _respond(client, sh, ref["id"], "INFO_REQUESTED").status_code == 422  # must say what is needed
    r = _respond(client, sh, ref["id"], "INFO_REQUESTED", message="Please bring the transfer certificate")
    assert r.status_code == 200 and r.json()["status"] == "INFO_REQUESTED"
    d = _need(client, h, edu)
    assert d["status"] == "FOLLOW_UP_REQUIRED"
    assert any(f["action_type"] == "REQUEST_MISSING_INFO" and f["status"] == "OPEN" for f in d["follow_ups"])
    seen = client.get(f"{API}/needs/{edu}/referrals", headers=h).json()[0]
    assert "transfer certificate" in seen["provider_responses"][0]["message"]

    c = client.post(f"{API}/needs/{edu}/contact-attempts", headers=h, json={
        "referral_id": ref["id"], "method": "MESSAGE", "result": "OTHER", "note": "Certificate sent"})
    assert c.status_code == 201
    detail = client.get(f"{P}/referrals/{ref['id']}", headers=sh).json()
    assert [m["note"] for m in detail["family_messages"]] == ["Certificate sent"]

    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 200
    d = _need(client, h, edu)
    assert d["status"] == "REFERRED"
    assert not [f for f in d["follow_ups"]
                if f["action_type"] == "REQUEST_MISSING_INFO" and f["status"] == "OPEN"]


def test_decline_creates_barrier_and_alternative_followup(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    assert _respond(client, sh, ref["id"], "DECLINED").status_code == 422  # reason required
    r = _respond(client, sh, ref["id"], "DECLINED", barrier="No places in Class 3")
    assert r.status_code == 200 and r.json()["status"] == "DECLINED"
    d = _need(client, h, edu)
    assert d["status"] == "BARRIER_IDENTIFIED" and d["is_open"] is True
    assert "No places in Class 3" in d["status_explanation"]
    assert any(f["action_type"] == "EXPLORE_ALTERNATIVE" and f["status"] == "OPEN" for f in d["follow_ups"])
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 409  # closed referral

    alt = make_listing(db, "School C", EDU)
    r = client.post(f"{API}/needs/{edu}/referrals", headers=h, json={"service_listing_id": str(alt.id)})
    assert r.status_code == 201
    assert _need(client, h, edu)["status"] == "REFERRED"


def test_decline_keeps_need_referred_while_another_referral_is_active(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    other = make_listing(db, "School B", EDU)
    assert client.post(f"{API}/needs/{edu}/referrals", headers=h,
                       json={"service_listing_id": str(other.id)}).status_code == 201
    assert _respond(client, sh, ref["id"], "DECLINED", barrier="Full").status_code == 200
    assert _need(client, h, edu)["status"] == "REFERRED"


def test_provider_confirmation_requires_acceptance_and_is_verified(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    assert _confirm(client, sh, ref["id"]).status_code == 409   # not accepted yet
    assert _need(client, h, edu)["status"] == "REFERRED"
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 200
    assert _need(client, h, edu)["status"] == "REFERRED"        # accepted is still not support received

    assert _confirm(client, sh, ref["id"], reference_note="Admission no. 1042").status_code == 200
    d = _need(client, h, edu)
    assert d["status"] == "SUPPORT_CONFIRMED" and d["is_open"] is False
    c = d["confirmations"][0]
    assert c["provider_verified"] is True and c["method"] == "PROVIDER_CONFIRMED"
    assert c["confirmed_by_role"] == "SCHOOL"
    assert not [f for f in d["follow_ups"] if f["status"] in ("OPEN", "IN_PROGRESS")]
    t = _totals(client, h, fam["id"])
    assert t["support_confirmed_by_provider"] == 1 and t["support_confirmed_by_family"] == 0
    assert _confirm(client, sh, ref["id"]).status_code == 409   # no duplicate confirmation


def test_provider_confirmation_upgrades_a_family_report(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 200
    r = client.post(f"{API}/needs/{edu}/confirm", headers=h,
                    json={"outcome": "Admitted", "method": "FAMILY_REPORTED"})
    assert r.status_code == 200
    t = _totals(client, h, fam["id"])
    assert t["support_confirmed_by_family"] == 1 and t["support_confirmed_by_provider"] == 0

    assert _confirm(client, sh, ref["id"]).status_code == 200
    t = _totals(client, h, fam["id"])
    assert t["support_confirmed_by_provider"] == 1 and t["support_confirmed_by_family"] == 0
    assert len(_need(client, h, edu)["confirmations"]) == 2   # history keeps both


def test_protection_outcome_only_through_authorised_provider(client, db):
    h, fam, child, mig, needs = journey(client, db)
    prot = needs["PROTECTION"]["id"]
    assert client.post(f"{API}/needs/{prot}/status", headers=h, json={"status": "PENDING"}).status_code == 200
    org, ngo, listing = make_provider(db, role=Role.NGO, email="ngo-prov@example.com",
                                      org_name="Child Help NGO", listing_name="Child Help")
    teacher = make_user(db, "school-same-org@example.com", Role.SCHOOL, organization_id=org.id)
    nh, th = auth_headers(client, ngo.email), auth_headers(client, teacher.email)
    ref = client.post(f"{API}/needs/{prot}/referrals", headers=h,
                      json={"service_listing_id": str(listing.id)}).json()

    assert client.get(f"{P}/referrals/{ref['id']}", headers=th).status_code == 404  # wrong category for role
    assert _respond(client, nh, ref["id"], "ACCEPTED").status_code == 200
    assert _confirm(client, nh, ref["id"], "Child placed with a caseworker").status_code == 200
    d = _need(client, h, prot)
    assert d["status"] == "SUPPORT_CONFIRMED" and d["confirmations"][0]["provider_verified"] is True


def test_provider_cannot_act_on_withdrawn_referral(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    assert client.post(f"{API}/referrals/{ref['id']}/withdraw", headers=h).status_code == 200
    assert client.get(f"{P}/referrals/{ref['id']}", headers=sh).json()["status"] == "WITHDRAWN"
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 409
    assert _confirm(client, sh, ref["id"]).status_code == 409


def test_provider_cannot_respond_once_family_closed_the_need(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    r = client.post(f"{API}/needs/{edu}/status", headers=h,
                    json={"status": "CLOSED", "reason": "Family decided to stay"})
    assert r.status_code == 200
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 409
    assert _confirm(client, sh, ref["id"]).status_code == 409
    assert _need(client, h, edu)["status"] == "CLOSED"


def test_family_can_mark_no_response_after_a_week(client, db):
    h, fam, edu, ref, sh, listing = _setup(client, db)
    url = f"{API}/referrals/{ref['id']}/no-response"
    assert client.post(url, headers=h).status_code == 409          # too early
    row = db.get(Referral, uuid.UUID(ref["id"]))
    row.referred_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.flush()
    r = client.post(url, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "NO_RESPONSE"
    d = _need(client, h, edu)
    assert d["status"] == "FOLLOW_UP_REQUIRED" and d["is_open"] is True
    assert any(f["status"] == "OPEN" for f in d["follow_ups"])
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 409
    again = client.post(f"{API}/needs/{edu}/referrals", headers=h,
                        json={"service_listing_id": str(listing.id)})
    assert again.status_code == 201                                  # can try the same service again


def test_provider_dashboard_counts(client, db):
    h, fam, edu, ref, sh, _ = _setup(client, db)
    d = client.get(f"{P}/dashboard", headers=sh).json()
    assert d["awaiting_response"] == 1 and d["accepted_awaiting_outcome"] == 0 and d["confirmed_outcomes"] == 0
    assert _respond(client, sh, ref["id"], "ACCEPTED").status_code == 200
    d = client.get(f"{P}/dashboard", headers=sh).json()
    assert d["awaiting_response"] == 0 and d["accepted_awaiting_outcome"] == 1
    assert _confirm(client, sh, ref["id"]).status_code == 200
    d = client.get(f"{P}/dashboard", headers=sh).json()
    assert d["accepted_awaiting_outcome"] == 0 and d["confirmed_outcomes"] == 1
    assert d["by_status"]["ACCEPTED"] == 1