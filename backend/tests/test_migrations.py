import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.models import AuditEvent
from tests.helpers import auth_headers, create_family, create_migration, make_user


def _owner_family(client, db):
    make_user(db, "mig-owner@example.com")
    h = auth_headers(client, "mig-owner@example.com")
    return h, create_family(client, h)


def _status(client, h, mig_id, new_status, **extra):
    return client.post(f"/api/v1/migrations/{mig_id}/status", headers=h,
                       json={"status": new_status, **extra})


def _events(db, mig_id, action):
    return db.scalars(select(AuditEvent).where(
        AuditEvent.entity_id == uuid.UUID(mig_id), AuditEvent.action == action)).all()


def test_new_migration_is_planned(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    assert mig["status"] == "PLANNED" and mig["actual_date"] is None


def test_valid_lifecycle_sets_actual_date_and_is_audited(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    r = _status(client, h, mig["id"], "ACTIVE")
    assert r.status_code == 200 and r.json()["actual_date"] is not None
    r = _status(client, h, mig["id"], "COMPLETED")
    assert r.status_code == 200 and r.json()["status"] == "COMPLETED"
    pairs = {(e.from_value, e.to_value) for e in _events(db, mig["id"], "MIGRATION_STATUS_CHANGED")}
    assert pairs == {("PLANNED", "ACTIVE"), ("ACTIVE", "COMPLETED")}


def test_invalid_transitions_are_rejected(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    assert _status(client, h, mig["id"], "COMPLETED").status_code == 409  # skipped ACTIVE
    assert _status(client, h, mig["id"], "PLANNED").status_code == 409
    assert _status(client, h, mig["id"], "ACTIVE").status_code == 200
    assert _status(client, h, mig["id"], "COMPLETED").status_code == 200
    assert _status(client, h, mig["id"], "ACTIVE").status_code == 409
    assert _status(client, h, mig["id"], "CANCELLED").status_code == 409


def test_only_one_active_migration_per_family(client, db):
    h, fam = _owner_family(client, db)
    first = create_migration(client, h, fam["id"])
    second = create_migration(client, h, fam["id"], destination_district="Nagpur")
    assert _status(client, h, first["id"], "ACTIVE").status_code == 200
    assert _status(client, h, second["id"], "ACTIVE").status_code == 409


def test_places_locked_after_move_starts(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    m = f"/api/v1/migrations/{mig['id']}"
    assert _status(client, h, mig["id"], "ACTIVE").status_code == 200
    assert client.patch(m, headers=h, json={"destination_district": "Nashik"}).status_code == 409
    assert client.patch(m, headers=h, json={"notes": "Moving by bus"}).status_code == 200


def test_editing_planned_destination_is_audited(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    r = client.patch(f"/api/v1/migrations/{mig['id']}", headers=h,
                     json={"destination_district": "Nagpur"})
    assert r.status_code == 200 and r.json()["destination_district"] == "Nagpur"
    events = _events(db, mig["id"], "MIGRATION_DESTINATION_CHANGED")
    assert len(events) == 1
    assert (events[0].from_value, events[0].to_value) == ("Pune", "Nagpur")


def test_origin_and_destination_must_differ(client, db):
    h, fam = _owner_family(client, db)
    r = client.post(f"/api/v1/families/{fam['id']}/migrations", headers=h, json={
        "origin_district": "Pune", "origin_state": "Maharashtra",
        "destination_district": "pune", "destination_state": "maharashtra"})
    assert r.status_code == 422
    mig = create_migration(client, h, fam["id"])  # Beed -> Pune
    r = client.patch(f"/api/v1/migrations/{mig['id']}", headers=h,
                     json={"destination_district": "Beed"})
    assert r.status_code == 422


def test_completed_and_cancelled_are_final(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    r = _status(client, h, mig["id"], "CANCELLED", reason="Work fell through")
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"
    assert client.patch(f"/api/v1/migrations/{mig['id']}", headers=h,
                        json={"notes": "late edit"}).status_code == 409
    assert _status(client, h, mig["id"], "ACTIVE").status_code == 409


def test_actual_date_cannot_be_in_the_future(client, db):
    h, fam = _owner_family(client, db)
    mig = create_migration(client, h, fam["id"])
    future = (date.today() + timedelta(days=3)).isoformat()
    assert _status(client, h, mig["id"], "ACTIVE", actual_date=future).status_code == 422