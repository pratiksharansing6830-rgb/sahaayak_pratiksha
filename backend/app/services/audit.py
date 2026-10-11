import uuid

from sqlalchemy.orm import Session

from app.models import AuditEvent, User


def log_event(
    db: Session,
    *,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    from_value: str | None = None,
    to_value: str | None = None,
    reason: str | None = None,
) -> AuditEvent:
    """Add an audit event to the current transaction (the caller commits).

    Never pass names, phone numbers, emails or medical details here.
    """
    event = AuditEvent(
        actor_user_id=actor.id if actor else None,
        actor_role=actor.role if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        from_value=from_value,
        to_value=to_value,
        reason=reason,
    )
    db.add(event)
    return event