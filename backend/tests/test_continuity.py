from tests.helpers import assess, create_child, journey

API = "/api/v1"


def _summary(client, h, family_id):
    r = client.get(f"{API}/families/{family_id}/continuity-summary", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def test_assess_creates_one_need_per_category_with_explanations(client, db):
    h, fam, child, mig, needs = journey(client, db)
    assert set(needs) == {"EDUCATION", "HEALTHCARE", "NUTRITION", "WELLBEING", "PROTECTION", "INCLUSION"}
    assert needs["EDUCATION"]["status"] == "PENDING"          # not enrolled: a known gap
    assert needs["HEALTHCARE"]["status"] == "NEEDS_ASSESSMENT"  # unknown is not "fine"
    for n in needs.values():
        assert n["is_open"] is True
        assert n["status_explanation"] and n["next_action"] and n["due_date"]


def test_assess_twice_creates_no_duplicates(client, db):
    h, fam, child, mig, needs = journey(client, db)
    again = assess(client, h, mig["id"])
    assert again["created_needs"] == 0 and again["existing_needs"] == 6
    assert len(client.get(f"{API}/families/{fam['id']}/needs", headers=h).json()) == 6
    follow_ups = client.get(f"{API}/families/{fam['id']}/follow-ups", headers=h).json()
    assert len(follow_ups) == 6                      # one active follow-up per need, no more
    assert {f["need_id"] for f in follow_ups} == {n["id"] for n in needs.values()}
    assert all(f["status"] == "OPEN" for f in follow_ups)


def test_reassessing_after_adding_a_child_only_adds_the_new_needs(client, db):
    h, fam, child, mig, needs = journey(client, db)
    create_child(client, h, fam["id"], name="Ravi", age=5)
    r = assess(client, h, mig["id"])
    assert r["created_needs"] == 6 and r["existing_needs"] == 6


def test_missing_assessment_is_not_treated_as_no_need(client, db):
    h, fam, child, mig, needs = journey(client, db, do_assess=False)
    s = _summary(client, h, fam["id"])
    assert s["totals"]["not_assessed"] == 6
    assert s["totals"]["not_required"] == 0
    assert s["children"][0]["needs"] == []
    assert len(s["children"][0]["not_assessed_categories"]) == 6


def test_cancelled_migration_cannot_be_assessed(client, db):
    h, fam, child, mig, needs = journey(client, db, do_assess=False)
    r = client.post(f"{API}/migrations/{mig['id']}/status", headers=h, json={"status": "CANCELLED"})
    assert r.status_code == 200
    assert client.post(f"{API}/migrations/{mig['id']}/assess", headers=h).status_code == 409


def test_status_changes_are_validated_and_recorded(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = needs["EDUCATION"]["id"]
    r = client.post(f"{API}/needs/{edu}/status", headers=h, json={
        "status": "BARRIER_IDENTIFIED", "reason": "School asked for a transfer certificate"})
    assert r.status_code == 200 and r.json()["status"] == "BARRIER_IDENTIFIED"
    detail = client.get(f"{API}/needs/{edu}", headers=h).json()
    pairs = {(e["from_status"], e["to_status"]) for e in detail["history"]}
    assert pairs == {(None, "PENDING"), ("PENDING", "BARRIER_IDENTIFIED")}
    active = [f for f in detail["follow_ups"] if f["status"] in ("OPEN", "IN_PROGRESS")]
    assert len(active) == 1


def test_invalid_and_system_only_transitions_are_rejected(client, db):
    h, fam, child, mig, needs = journey(client, db)
    health = needs["HEALTHCARE"]["id"]  # NEEDS_ASSESSMENT
    url = f"{API}/needs/{health}/status"
    assert client.post(url, headers=h, json={"status": "CLOSED", "reason": "no longer needed"}).status_code == 409
    for s in ("SUPPORT_CONFIRMED", "REFERRED", "AWAITING_PROVIDER_RESPONSE", "REVIEW_REQUIRED"):
        assert client.post(url, headers=h, json={"status": s}).status_code == 409, s
    assert client.post(url, headers=h, json={"status": "NOT_REQUIRED"}).status_code == 422  # no reason
    assert client.get(f"{API}/needs/{health}", headers=h).json()["status"] == "NEEDS_ASSESSMENT"


def test_not_required_needs_a_reason_and_is_not_support_received(client, db):
    h, fam, child, mig, needs = journey(client, db)
    nutrition = needs["NUTRITION"]["id"]
    r = client.post(f"{API}/needs/{nutrition}/status", headers=h, json={
        "status": "NOT_REQUIRED", "reason": "Child gets meals at the home school"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_open"] is False and body["closure_reason"]

    detail = client.get(f"{API}/needs/{nutrition}", headers=h).json()
    assert not [f for f in detail["follow_ups"] if f["status"] in ("OPEN", "IN_PROGRESS")]

    totals = _summary(client, h, fam["id"])["totals"]
    assert totals["not_required"] == 1
    assert totals["support_confirmed_by_family"] == 0 and totals["support_confirmed_by_provider"] == 0

    r = client.post(f"{API}/needs/{nutrition}/status", headers=h, json={"status": "NEEDS_ASSESSMENT"})
    assert r.status_code == 200 and r.json()["is_open"] is True and r.json()["closure_reason"] is None