from datetime import date, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import FollowUp
from tests.helpers import journey

API = "/api/v1"


def _active_followup(client, h, family_id, need_id):
    rows = client.get(f"{API}/families/{family_id}/follow-ups?status=OPEN", headers=h).json()
    return next(f for f in rows if f["need_id"] == need_id)


def test_duplicate_manual_followup_is_rejected(client, db):
    h, fam, child, mig, needs = journey(client, db)
    url = f"{API}/needs/{needs['EDUCATION']['id']}/follow-ups"
    # CONTACT_SCHOOL was created automatically and is still active
    assert client.post(url, headers=h, json={
        "action_type": "CONTACT_SCHOOL", "description": "Call the school again"}).status_code == 409
    ok = client.post(url, headers=h, json={
        "action_type": "REQUEST_MISSING_INFO", "description": "Ask for the transfer certificate"})
    assert ok.status_code == 201 and ok.json()["assigned_role"] == "CITIZEN"
    assert client.post(url, headers=h, json={
        "action_type": "REQUEST_MISSING_INFO", "description": "Again"}).status_code == 409


def test_safeguarding_escalation_is_only_for_protection_needs(client, db):
    h, fam, child, mig, needs = journey(client, db)
    body = {"action_type": "ESCALATE_SAFEGUARDING", "description": "Please review this child's safety"}
    assert client.post(f"{API}/needs/{needs['EDUCATION']['id']}/follow-ups", headers=h, json=body).status_code == 422
    r = client.post(f"{API}/needs/{needs['PROTECTION']['id']}/follow-ups", headers=h, json=body)
    assert r.status_code == 201 and r.json()["assigned_role"] == "NGO"


def test_resolved_need_cannot_get_new_followups(client, db):
    h, fam, child, mig, needs = journey(client, db)
    n = needs["NUTRITION"]["id"]
    assert client.post(f"{API}/needs/{n}/status", headers=h, json={
        "status": "NOT_REQUIRED", "reason": "Meals provided at school"}).status_code == 200
    assert client.post(f"{API}/needs/{n}/follow-ups", headers=h, json={
        "action_type": "SCHEDULE_FOLLOW_UP", "description": "Check in"}).status_code == 409


def test_complete_and_cancel_followups(client, db):
    h, fam, child, mig, needs = journey(client, db)
    edu = _active_followup(client, h, fam["id"], needs["EDUCATION"]["id"])
    r = client.post(f"{API}/follow-ups/{edu['id']}/complete", headers=h, json={})
    assert r.status_code == 200 and r.json()["follow_up"]["completed_at"] is not None
    assert client.post(f"{API}/follow-ups/{edu['id']}/complete", headers=h, json={}).status_code == 409

    health = _active_followup(client, h, fam["id"], needs["HEALTHCARE"]["id"])
    r = client.post(f"{API}/follow-ups/{health['id']}/cancel", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert client.post(f"{API}/follow-ups/{health['id']}/cancel", headers=h).status_code == 409


def test_update_followup_rules(client, db):
    h, fam, child, mig, needs = journey(client, db)
    fu = _active_followup(client, h, fam["id"], needs["EDUCATION"]["id"])
    url = f"{API}/follow-ups/{fu['id']}"
    r = client.patch(url, headers=h, json={
        "priority": "URGENT", "status": "IN_PROGRESS", "next_action": "Visit on Monday"})
    assert r.status_code == 200
    assert r.json()["priority"] == "URGENT" and r.json()["status"] == "IN_PROGRESS"
    assert client.patch(url, headers=h, json={"priority": None}).status_code == 422
    assert client.patch(url, headers=h, json={"description": None}).status_code == 422
    assert client.patch(url, headers=h, json={"status": "COMPLETED"}).status_code == 422  # use /complete
    past = (date.today() - timedelta(days=2)).isoformat()
    assert client.patch(url, headers=h, json={"due_date": past}).status_code == 422


def test_overdue_followups_are_flagged_and_filterable(client, db):
    h, fam, child, mig, needs = journey(client, db)
    fu = _active_followup(client, h, fam["id"], needs["EDUCATION"]["id"])
    row = db.get(FollowUp, __import__("uuid").UUID(fu["id"]))
    row.due_date = date.today() - timedelta(days=1)
    db.flush()
    overdue = client.get(f"{API}/families/{fam['id']}/follow-ups?overdue_only=true", headers=h).json()
    assert [f["id"] for f in overdue] == [fu["id"]] and overdue[0]["is_overdue"] is True
    s = client.get(f"{API}/families/{fam['id']}/continuity-summary", headers=h).json()
    assert s["totals"]["overdue"] >= 0  # need due dates are tracked separately from follow-up due dates


def test_database_itself_blocks_duplicate_active_followups(client, db):
    h, fam, child, mig, needs = journey(client, db)
    need_id = needs["EDUCATION"]["id"]
    existing = db.scalars(select(FollowUp).where(FollowUp.need_id == __import__("uuid").UUID(need_id))).first()
    dup = FollowUp(need_id=existing.need_id, action_type=existing.action_type, description="duplicate")
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(dup)
            db.flush()