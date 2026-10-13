import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.v1.referrals import ACTIVE_REFERRAL, _referral_out
from app.core.database import get_db
from app.models import NeedStatus, Priority, Referral, ReferralStatus, Role, User
from app.schemas.referral import ReferralOut
from app.services.access import get_referral_for_user
from app.services.audit import log_event
from app.services.continuity import ACTION_FOR, transition_need
from app.services.provider import add_followup

router = APIRouter(tags=["referrals"])
citizen_only = require_roles(Role.CITIZEN)

NO_RESPONSE_AFTER_DAYS = 7


@router.post("/referrals/{referral_id}/no-response", response_model=ReferralOut)
def mark_no_response(referral_id: uuid.UUID, user: User = Depends(citizen_only), db: Session = Depends(get_db)):
    ref, need, _, _ = get_referral_for_user(db, user, referral_id, write=True)
    if ref.status != ReferralStatus.RECORDED:
        raise HTTPException(409, "Only a referral the provider has not answered can be marked as no response.")
    if datetime.now(timezone.utc) - ref.referred_at < timedelta(days=NO_RESPONSE_AFTER_DAYS):
        raise HTTPException(409, f"Please allow {NO_RESPONSE_AFTER_DAYS} days for the provider to respond.")

    ref.status = ReferralStatus.NO_RESPONSE
    db.flush()
    log_event(db, actor=user, action="REFERRAL_NO_RESPONSE", entity_type="referral",
              entity_id=ref.id, from_value="RECORDED", to_value="NO_RESPONSE")
    others = db.scalar(select(Referral.id).where(
        Referral.need_id == need.id, Referral.id != ref.id,
        Referral.status.in_(ACTIVE_REFERRAL)).limit(1))
    if others is None:
        if need.status in (NeedStatus.REFERRED, NeedStatus.AWAITING_PROVIDER_RESPONSE):
            transition_need(
                db, need, NeedStatus.FOLLOW_UP_REQUIRED, user, reason="Provider did not respond",
                explanation="The provider has not responded to the referral. Follow up or try another service.")
        add_followup(db, need, ACTION_FOR[need.category],
                     "The provider has not responded. Follow up with them or look for another service.",
                     user, priority=Priority.HIGH, referral_id=ref.id)
    db.commit()
    db.refresh(ref)
    return _referral_out(db, ref)