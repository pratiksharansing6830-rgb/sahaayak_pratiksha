from app.models import Role
from tests.helpers import assess, auth_headers, create_migration, journey, make_user

API = "/api/v1"


def _confirm(client, h, need_id, method="FAMILY_REPORTED", **extra):
    return client.post(f"{API}/needs/{need_id}/confirm", headers=h,
                       json={"outcome": "Admitted to Class 3", "method": method, **extra})


def _summary(client, h, family_id):
    return client.get(f"{API}/families/{family_id}/continuity-summary", headers=h).json()


def test_family_confirmation_is_labelled_unverified(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    r = _confirm(client, h, edu)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "SUPPORT_CONFIRMED" and d["is_open"] is False
    c = d["confirmations"][0]
    assert c["provider_verified"] is False and c["method"] == "FAMILY_REPORTED"
    assert c["confirmed_by_role"] == "CITIZEN"
    assert "provider" in d["status_explanation"].lower()
    totals = _summary(client, h, fam["id"])["totals"]
    assert totals["support_confirmed_by_family"] == 1 and totals["support_confirmed_by_provider"] == 0


def test_citizen_cannot_record_provider_confirmation(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    for method in ("PROVIDER_CONFIRMED", "SUPPORT_WORKER_OBSERVED"):
        assert _confirm(client, h, edu, method).status_code == 403
    d = client.get(f"{API}/needs/{edu}", headers=h).json()
    assert d["status"] == "PENDING" and d["confirmations"] == []


def test_unassessed_need_cannot_be_confirmed(client, db):
    h, fam, child, mig, needs = journey(client, db)
    assert _confirm(client, h, needs["HEALTHCARE"]["id"]).status_code == 409


def test_protection_need_cannot_be_confirmed_by_a_citizen(client, db):
    h, fam, child, mig, needs = journey(client, db)
    prot = needs["PROTECTION"]["id"]
    assert client.post(f"{API}/needs/{prot}/status", headers=h, json={"status": "PENDING"}).status_code == 200
    assert _confirm(client, h, prot).status_code == 403
    d = client.get(f"{API}/needs/{prot}", headers=h).json()
    assert d["status"] == "PENDING" and d["confirmations"] == []


def test_document_confirmation_needs_a_reference(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    assert _confirm(client, h, edu, "DOCUMENT_SEEN").status_code == 422
    r = _confirm(client, h, edu, "DOCUMENT_SEEN", reference_note="Admission receipt shown by the school")
    assert r.status_code == 200 and r.json()["confirmations"][0]["method"] == "DOCUMENT_SEEN"


def test_completing_a_followup_does_not_resolve_the_need(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    detail = client.get(f"{API}/needs/{edu}", headers=h).json()
    fu = [f for f in detail["follow_ups"] if f["status"] == "OPEN"][0]
    r = client.post(f"{API}/follow-ups/{fu['id']}/complete", headers=h,
                    json={"next_action": "Wait for the school to reply"})
    assert r.status_code == 200
    body = r.json()
    assert body["follow_up"]["status"] == "COMPLETED"
    assert body["need"]["status"] == "PENDING" and body["need"]["is_open"] is True


def test_resolving_a_need_closes_its_active_followups(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    assert _confirm(client, h, edu).status_code == 200
    detail = client.get(f"{API}/needs/{edu}", headers=h).json()
    assert detail["follow_ups"]
    assert not [f for f in detail["follow_ups"] if f["status"] in ("OPEN", "IN_PROGRESS")]
    assert any(f["status"] == "CANCELLED" for f in detail["follow_ups"])


def test_completed_migration_does_not_confirm_any_service(client, db):
    h, fam, child, mig, needs = journey(client, db)
    for st in ("ACTIVE", "COMPLETED"):
        assert client.post(f"{API}/migrations/{mig['id']}/status", headers=h,
                           json={"status": st}).status_code == 200
    s = _summary(client, h, fam["id"])
    assert s["totals"]["open"] == 6 and len(s["unresolved"]) == 6
    assert s["totals"]["support_confirmed_by_family"] == 0
    assert s["totals"]["support_confirmed_by_provider"] == 0


def test_new_destination_does_not_inherit_old_confirmation(client, db):
    h, fam, child, migA, needsA = journey(client, db)
    edu_a = needsA["EDUCATION"]["id"]
    assert _confirm(client, h, edu_a).status_code == 200

    migB = create_migration(client, h, fam["id"], destination_district="Nagpur")
    byc = {n["category"]: n for n in assess(client, h, migB["id"])["needs"]}
    assert byc["EDUCATION"]["id"] != edu_a
    assert byc["EDUCATION"]["migration_id"] == migB["id"]
    assert byc["EDUCATION"]["status"] == "PENDING" and byc["EDUCATION"]["is_open"] is True

    assert client.get(f"{API}/needs/{edu_a}", headers=h).json()["status"] == "SUPPORT_CONFIRMED"
    unresolved_ids = {u["need_id"] for u in _summary(client, h, fam["id"])["unresolved"]}
    assert byc["EDUCATION"]["id"] in unresolved_ids


def test_changing_planned_destination_sends_confirmed_needs_back_for_review(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    assert _confirm(client, h, edu).status_code == 200
    r = client.patch(f"{API}/migrations/{mig['id']}", headers=h, json={"destination_district": "Nagpur"})
    assert r.status_code == 200
    d = client.get(f"{API}/needs/{edu}", headers=h).json()
    assert d["status"] == "REVIEW_REQUIRED" and d["is_open"] is True
    assert any(f["status"] == "OPEN" for f in d["follow_ups"])
    assert len(d["confirmations"]) == 1  # history is kept


def test_other_family_cannot_touch_needs(client, db):
    h, fam, child, mig, needs = journey(client, db)
    make_user(db, "intruder@example.com")
    o = auth_headers(client, "intruder@example.com")
    edu = needs["EDUCATION"]["id"]
    fu = client.get(f"{API}/needs/{edu}", headers=h).json()["follow_ups"][0]["id"]
    f = f"{API}/families/{fam['id']}"
    for url in (f"{API}/needs/{edu}", f"{f}/needs", f"{f}/continuity-summary", f"{f}/follow-ups",
                f"{API}/children/{child['id']}/needs"):
        assert client.get(url, headers=o).status_code == 404, url
    assert client.post(f"{API}/needs/{edu}/status", headers=o, json={"status": "PENDING"}).status_code == 404
    assert _confirm(client, o, edu).status_code == 404
    assert client.post(f"{API}/migrations/{mig['id']}/assess", headers=o).status_code == 404
    assert client.post(f"{API}/follow-ups/{fu}/complete", headers=o, json={}).status_code == 404
    assert client.post(f"{API}/needs/{edu}/follow-ups", headers=o, json={
        "action_type": "SCHEDULE_FOLLOW_UP", "description": "x"}).status_code == 404
    assert client.get(f"{API}/needs/{edu}", headers=h).json()["status"] == "PENDING"


def test_support_worker_can_read_shared_needs_but_not_change_them(client, db):
    h, fam, child, mig, needs = journey(client, db)
    make_user(db, "ngo@example.com", Role.NGO)
    ngo = auth_headers(client, "ngo@example.com")
    edu = needs["EDUCATION"]["id"]
    assert client.get(f"{API}/needs/{edu}", headers=ngo).status_code == 404  # not shared yet

    r = client.post(f"{API}/families/{fam['id']}/access", headers=h, json={"email": "ngo@example.com"})
    assert r.status_code == 201
    assert client.get(f"{API}/needs/{edu}", headers=ngo).status_code == 200
    assert client.get(f"{API}/families/{fam['id']}/continuity-summary", headers=ngo).status_code == 200
    fu = client.get(f"{API}/needs/{edu}", headers=ngo).json()["follow_ups"][0]["id"]
    assert client.post(f"{API}/needs/{edu}/status", headers=ngo, json={"status": "BARRIER_IDENTIFIED"}).status_code == 403
    assert _confirm(client, ngo, edu).status_code == 403
    assert client.post(f"{API}/follow-ups/{fu}/complete", headers=ngo, json={}).status_code == 403
    assert client.post(f"{API}/migrations/{mig['id']}/assess", headers=ngo).status_code == 403


def test_non_family_roles_cannot_see_needs(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    for i, role in enumerate([Role.ADMIN, Role.GOVERNMENT, Role.SCHOOL, Role.HEALTHCARE]):
        make_user(db, f"role{i}@example.com", role)
        rh = auth_headers(client, f"role{i}@example.com")
        assert client.get(f"{API}/needs/{edu}", headers=rh).status_code == 403
        assert client.get(f"{API}/families/{fam['id']}/continuity-summary", headers=rh).status_code == 403