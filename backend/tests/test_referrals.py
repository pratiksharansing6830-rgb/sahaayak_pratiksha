import uuid

from app.models import Role, ServiceCategory
from tests.helpers import auth_headers, journey, make_listing, make_user

API = "/api/v1"
EDU, HEALTH, NUTR = ServiceCategory.EDUCATION, ServiceCategory.HEALTHCARE, ServiceCategory.NUTRITION


def _refer(client, h, need_id, listing_id, note=None):
    body = {"service_listing_id": str(listing_id)}
    if note:
        body["note"] = note
    return client.post(f"{API}/needs/{need_id}/referrals", headers=h, json=body)


def _need(client, h, need_id):
    return client.get(f"{API}/needs/{need_id}", headers=h).json()


def test_listing_alone_is_not_a_referral(client, db):
    h, fam, child, mig, needs = journey(client, db)
    make_listing(db, "School A", EDU)
    found = client.get(f"{API}/services?district=Pune", headers=h).json()
    assert found["total"] == 1
    edu = needs["EDUCATION"]["id"]
    assert _need(client, h, edu)["status"] == "PENDING"
    assert client.get(f"{API}/needs/{edu}/referrals", headers=h).json() == []


def test_referral_moves_need_to_referred_but_not_to_support(client, db):
    h, fam, child, mig, needs = journey(client, db)
    school = make_listing(db, "School A", EDU)
    edu = needs["EDUCATION"]["id"]
    r = _refer(client, h, edu, school.id, "Family asked about Class 3")
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "RECORDED" and b["service_name"] == "School A"
    assert b["provider_responses"] == [] and "not responded" in b["plain_status"]

    d = _need(client, h, edu)
    assert d["status"] == "REFERRED" and d["is_open"] is True
    assert ("PENDING", "REFERRED") in {(e["from_status"], e["to_status"]) for e in d["history"]}
    s = client.get(f"{API}/families/{fam['id']}/continuity-summary", headers=h).json()
    assert s["totals"]["open"] == 6
    assert s["totals"]["support_confirmed_by_family"] == 0
    assert s["totals"]["support_confirmed_by_provider"] == 0


def test_unassessed_need_cannot_be_referred(client, db):
    h, fam, child, mig, needs = journey(client, db)
    clinic = make_listing(db, "Clinic", HEALTH)
    health = needs["HEALTHCARE"]["id"]  # NEEDS_ASSESSMENT
    assert _refer(client, h, health, clinic.id).status_code == 409
    assert client.get(f"{API}/needs/{health}/referrals", headers=h).json() == []
    assert _need(client, h, health)["status"] == "NEEDS_ASSESSMENT"


def test_wrong_category_and_missing_listing(client, db):
    h, fam, child, mig, needs = journey(client, db)
    clinic = make_listing(db, "Clinic", HEALTH)
    gone = make_listing(db, "Closed School", EDU)
    gone.is_active = False
    db.flush()
    edu = needs["EDUCATION"]["id"]
    assert _refer(client, h, edu, clinic.id).status_code == 422
    assert _refer(client, h, edu, gone.id).status_code == 404
    assert _refer(client, h, edu, uuid.uuid4()).status_code == 404
    assert _need(client, h, edu)["status"] == "PENDING"


def test_duplicate_and_alternative_referrals(client, db):
    h, fam, child, mig, needs = journey(client, db)
    a, b = make_listing(db, "School A", EDU), make_listing(db, "School B", EDU)
    edu = needs["EDUCATION"]["id"]
    assert _refer(client, h, edu, a.id).status_code == 201
    assert _refer(client, h, edu, a.id).status_code == 409
    assert _refer(client, h, edu, b.id).status_code == 201
    assert _need(client, h, edu)["status"] == "REFERRED"
    assert len(client.get(f"{API}/needs/{edu}/referrals", headers=h).json()) == 2


def test_contact_attempt_does_not_change_need(client, db):
    h, fam, child, mig, needs = journey(client, db)
    school = make_listing(db, "School A", EDU)
    edu = needs["EDUCATION"]["id"]
    url = f"{API}/needs/{edu}/contact-attempts"
    r = client.post(url, headers=h, json={
        "service_listing_id": str(school.id), "method": "PHONE", "result": "NO_ANSWER", "note": "Rang twice"})
    assert r.status_code == 201 and r.json()["service_name"] == "School A"
    assert _need(client, h, edu)["status"] == "PENDING"
    assert client.get(f"{API}/needs/{edu}/referrals", headers=h).json() == []
    assert len(client.get(url, headers=h).json()) == 1
    assert client.post(url, headers=h, json={"method": "PHONE", "result": "REACHED"}).status_code == 422

    ref = _refer(client, h, edu, school.id).json()
    nutrition = needs["NUTRITION"]["id"]  # a referral from another need must not be usable here
    assert client.post(f"{API}/needs/{nutrition}/contact-attempts", headers=h, json={
        "referral_id": ref["id"], "method": "VISIT", "result": "REACHED"}).status_code == 404


def test_contact_attempt_via_referral_uses_its_service(client, db):
    h, fam, child, mig, needs = journey(client, db)
    school = make_listing(db, "School A", EDU)
    edu = needs["EDUCATION"]["id"]
    ref = _refer(client, h, edu, school.id).json()
    r = client.post(f"{API}/needs/{edu}/contact-attempts", headers=h, json={
        "referral_id": ref["id"], "method": "VISIT", "result": "INFO_REQUESTED"})
    assert r.status_code == 201
    assert r.json()["service_listing_id"] == str(school.id) and r.json()["referral_id"] == ref["id"]


def test_withdrawing_referrals(client, db):
    h, fam, child, mig, needs = journey(client, db)
    a, b = make_listing(db, "School A", EDU), make_listing(db, "School B", EDU)
    edu = needs["EDUCATION"]["id"]
    ra, rb = _refer(client, h, edu, a.id).json(), _refer(client, h, edu, b.id).json()

    r = client.post(f"{API}/referrals/{ra['id']}/withdraw", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "WITHDRAWN"
    assert _need(client, h, edu)["status"] == "REFERRED"   # one active referral is left
    assert client.post(f"{API}/referrals/{ra['id']}/withdraw", headers=h).status_code == 409

    assert client.post(f"{API}/referrals/{rb['id']}/withdraw", headers=h).status_code == 200
    d = _need(client, h, edu)
    assert d["status"] == "PENDING" and d["is_open"] is True


def test_resolved_need_cannot_be_referred_or_contacted(client, db):
    h, fam, child, mig, needs = journey(client, db)
    n = needs["NUTRITION"]["id"]
    assert client.post(f"{API}/needs/{n}/status", headers=h, json={
        "status": "NOT_REQUIRED", "reason": "Meals provided at school"}).status_code == 200
    centre = make_listing(db, "Nutrition Centre", NUTR)
    assert _refer(client, h, n, centre.id).status_code == 409
    assert client.post(f"{API}/needs/{n}/contact-attempts", headers=h, json={
        "service_listing_id": str(centre.id), "method": "PHONE", "result": "REACHED"}).status_code == 409


def test_referral_access_rules(client, db):
    h, fam, child, mig, needs = journey(client, db)
    school = make_listing(db, "School A", EDU)
    edu = needs["EDUCATION"]["id"]
    ref = _refer(client, h, edu, school.id).json()

    make_user(db, "intruder@example.com")
    o = auth_headers(client, "intruder@example.com")
    assert client.get(f"{API}/needs/{edu}/referrals", headers=o).status_code == 404
    assert client.get(f"{API}/families/{fam['id']}/referrals", headers=o).status_code == 404
    assert _refer(client, o, edu, school.id).status_code == 404
    assert client.post(f"{API}/referrals/{ref['id']}/withdraw", headers=o).status_code == 404
    assert client.post(f"{API}/referrals/{uuid.uuid4()}/withdraw", headers=o).status_code == 404

    make_user(db, "ngo@example.com", Role.NGO)
    ngo = auth_headers(client, "ngo@example.com")
    assert client.get(f"{API}/needs/{edu}/referrals", headers=ngo).status_code == 404  # not shared
    assert client.post(f"{API}/families/{fam['id']}/access", headers=h,
                       json={"email": "ngo@example.com"}).status_code == 201
    assert client.get(f"{API}/needs/{edu}/referrals", headers=ngo).status_code == 200
    assert _refer(client, ngo, edu, school.id).status_code == 403
    assert client.post(f"{API}/referrals/{ref['id']}/withdraw", headers=ngo).status_code == 403

    for i, role in enumerate([Role.ADMIN, Role.GOVERNMENT, Role.SCHOOL, Role.HEALTHCARE]):
        make_user(db, f"role{i}@example.com", role)
        rh = auth_headers(client, f"role{i}@example.com")
        assert client.get(f"{API}/needs/{edu}/referrals", headers=rh).status_code == 403


def test_family_referral_and_contact_history(client, db):
    h, fam, child, mig, needs = journey(client, db)
    school, clinic = make_listing(db, "School A", EDU), make_listing(db, "Clinic", HEALTH)
    edu = needs["EDUCATION"]["id"]
    _refer(client, h, edu, school.id)
    client.post(f"{API}/needs/{edu}/contact-attempts", headers=h, json={
        "service_listing_id": str(school.id), "method": "PHONE", "result": "REACHED"})
    refs = client.get(f"{API}/families/{fam['id']}/referrals", headers=h).json()
    contacts = client.get(f"{API}/families/{fam['id']}/contact-attempts", headers=h).json()
    assert len(refs) == 1 and len(contacts) == 1
    assert refs[0]["service_name"] == "School A" and contacts[0]["result"] == "REACHED"