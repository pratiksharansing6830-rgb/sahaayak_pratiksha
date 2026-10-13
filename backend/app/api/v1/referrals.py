import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import (
    Child,
    ContactAttempt,
    Migration,
    NeedStatus,
    ProviderResponse,
    Referral,
    ReferralStatus,
    Role,
    ServiceListing,
    ServiceNeed,
    User,
)
from app.schemas.referral import (
    REFERRAL_TEXT,
    ContactAttemptCreate,
    ContactAttemptOut,
    ProviderResponseOut,
    ReferralCreate,
    ReferralOut,
)
from app.services.access import (
    get_family_access,
    get_need_for_user,
    get_referral_for_user,
)
from app.services.audit import log_event
from app.services.continuity import OPEN_STATUSES, transition_need

router = APIRouter(tags=["referrals"])
citizen_only = require_roles(Role.CITIZEN)
family_user = require_roles(Role.CITIZEN, Role.NGO)

S = NeedStatus
ACTIVE_REFERRAL = (
    ReferralStatus.RECORDED,
    ReferralStatus.ACCEPTED,
    ReferralStatus.INFO_REQUESTED,
)


def _listing(db: Session, listing_id, need: ServiceNeed) -> ServiceListing:
    service = db.scalar(
        select(ServiceListing).where(
            ServiceListing.id == listing_id,
            ServiceListing.is_active.is_(True),
        )
    )
    if service is None:
        raise HTTPException(404, "Service not found.")

    if service.category != need.category:
        raise HTTPException(
            422,
            f"This service is for {service.category.value}, "
            f"but the need is for {need.category.value}.",
        )

    return service


def _referral_out(db: Session, ref: Referral) -> ReferralOut:
    listing = (
        db.get(ServiceListing, ref.service_listing_id)
        if ref.service_listing_id
        else None
    )
    responses = db.scalars(
        select(ProviderResponse)
        .where(ProviderResponse.referral_id == ref.id)
        .order_by(ProviderResponse.responded_at)
    ).all()

    return ReferralOut(
        id=ref.id,
        need_id=ref.need_id,
        service_listing_id=ref.service_listing_id,
        service_name=listing.name if listing else None,
        service_verification_status=(
            listing.verification_status if listing else None
        ),
        status=ref.status,
        plain_status=REFERRAL_TEXT[ref.status],
        referred_at=ref.referred_at,
        note=ref.note,
        provider_responses=[
            ProviderResponseOut.model_validate(response)
            for response in responses
        ],
    )


def _contact_out(db: Session, contact: ContactAttempt) -> ContactAttemptOut:
    listing = (
        db.get(ServiceListing, contact.service_listing_id)
        if contact.service_listing_id
        else None
    )

    return ContactAttemptOut(
        id=contact.id,
        need_id=contact.need_id,
        referral_id=contact.referral_id,
        service_listing_id=contact.service_listing_id,
        service_name=listing.name if listing else None,
        method=contact.method,
        result=contact.result,
        attempted_at=contact.attempted_at,
        note=contact.note,
    )


# ---------------- Referrals ----------------
@router.post(
    "/needs/{need_id}/referrals",
    response_model=ReferralOut,
    status_code=201,
)
def record_referral(
    need_id: uuid.UUID,
    payload: ReferralCreate,
    user: User = Depends(citizen_only),
    db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id, write=True)

    if need.status not in OPEN_STATUSES:
        raise HTTPException(
            409,
            "This need is already resolved, so it cannot be referred.",
        )

    if need.status == S.NEEDS_ASSESSMENT:
        raise HTTPException(
            409,
            "Assess this need first. Mark it as pending once the need is confirmed.",
        )

    if need.status == S.REVIEW_REQUIRED:
        raise HTTPException(
            409,
            "Review this need first (move it back to pending), then record a referral.",
        )

    listing = _listing(db, payload.service_listing_id, need)

    if need.migration_id:
        migration = db.get(Migration, need.migration_id)
        if migration and listing.district != migration.destination_district:
            raise HTTPException(
                422,
                f"This service is in {listing.district}, but the move is to "
                f"{migration.destination_district}. "
                "Choose a service in the destination district.",
            )

    duplicate = db.scalar(
        select(Referral.id)
        .where(
            Referral.need_id == need.id,
            Referral.service_listing_id == listing.id,
            Referral.status.in_(ACTIVE_REFERRAL),
        )
        .limit(1)
    )

    if duplicate:
        raise HTTPException(
            409,
            "There is already an active referral to this service for this need.",
        )

    referral = Referral(
        need_id=need.id,
        service_listing_id=listing.id,
        created_by_user_id=user.id,
        note=payload.note,
    )
    db.add(referral)
    db.flush()

    log_event(
        db,
        actor=user,
        action="REFERRAL_RECORDED",
        entity_type="referral",
        entity_id=referral.id,
        to_value="RECORDED",
    )

    if need.status not in (S.REFERRED, S.AWAITING_PROVIDER_RESPONSE):
        transition_need(
            db,
            need,
            S.REFERRED,
            user,
            reason="Referral recorded",
        )

    db.commit()
    db.refresh(referral)
    return _referral_out(db, referral)


@router.get(
    "/needs/{need_id}/referrals",
    response_model=list[ReferralOut],
)
def list_need_referrals(
    need_id: uuid.UUID,
    user: User = Depends(family_user),
    db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id)

    referrals = db.scalars(
        select(Referral)
        .where(Referral.need_id == need.id)
        .order_by(Referral.referred_at.desc())
    ).all()

    return [_referral_out(db, referral) for referral in referrals]


@router.get(
    "/families/{family_id}/referrals",
    response_model=list[ReferralOut],
)
def list_family_referrals(
    family_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user),
    db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id)

    statement = (
        select(Referral)
        .join(ServiceNeed, ServiceNeed.id == Referral.need_id)
        .join(Child, Child.id == ServiceNeed.child_id)
        .where(
            Child.family_id == family.id,
            Child.deleted_at.is_(None),
        )
        .order_by(Referral.referred_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return [
        _referral_out(db, referral)
        for referral in db.scalars(statement).all()
    ]


@router.post(
    "/referrals/{referral_id}/withdraw",
    response_model=ReferralOut,
)
def withdraw_referral(
    referral_id: uuid.UUID,
    user: User = Depends(citizen_only),
    db: Session = Depends(get_db),
):
    referral, need, _, _ = get_referral_for_user(
        db, user, referral_id, write=True
    )

    if referral.status not in ACTIVE_REFERRAL:
        raise HTTPException(
            409,
            "Only an active referral can be withdrawn.",
        )

    old_status = referral.status
    referral.status = ReferralStatus.WITHDRAWN
    db.flush()

    log_event(
        db,
        actor=user,
        action="REFERRAL_WITHDRAWN",
        entity_type="referral",
        entity_id=referral.id,
        from_value=old_status.value,
        to_value="WITHDRAWN",
    )

    other_referral = db.scalar(
        select(Referral.id)
        .where(
            Referral.need_id == need.id,
            Referral.id != referral.id,
            Referral.status.in_(ACTIVE_REFERRAL),
        )
        .limit(1)
    )

    if (
        other_referral is None
        and need.status in (S.REFERRED, S.AWAITING_PROVIDER_RESPONSE)
    ):
        transition_need(
            db,
            need,
            S.PENDING,
            user,
            reason="Referral withdrawn",
        )

    db.commit()
    db.refresh(referral)
    return _referral_out(db, referral)


# ---------------- Contact attempts ----------------
@router.post(
    "/needs/{need_id}/contact-attempts",
    response_model=ContactAttemptOut,
    status_code=201,
)
def record_contact_attempt(
    need_id: uuid.UUID,
    payload: ContactAttemptCreate,
    user: User = Depends(citizen_only),
    db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id, write=True)

    if need.status not in OPEN_STATUSES:
        raise HTTPException(409, "This need is already resolved.")

    listing_id = payload.service_listing_id

    if payload.referral_id:
        referral = db.get(Referral, payload.referral_id)

        if referral is None or referral.need_id != need.id:
            raise HTTPException(404, "Referral not found.")

        if listing_id and listing_id != referral.service_listing_id:
            raise HTTPException(
                422,
                "That service does not match the referral.",
            )

        listing_id = referral.service_listing_id
    else:
        listing_id = _listing(db, listing_id, need).id

    contact = ContactAttempt(
        need_id=need.id,
        referral_id=payload.referral_id,
        service_listing_id=listing_id,
        user_id=user.id,
        method=payload.method,
        result=payload.result,
        note=payload.note,
    )
    db.add(contact)
    db.flush()

    # A contact attempt is history only. It never changes the need's status.
    log_event(
        db,
        actor=user,
        action="CONTACT_ATTEMPT_RECORDED",
        entity_type="contact_attempt",
        entity_id=contact.id,
        to_value=payload.result.value,
    )

    db.commit()
    db.refresh(contact)
    return _contact_out(db, contact)


@router.get(
    "/needs/{need_id}/contact-attempts",
    response_model=list[ContactAttemptOut],
)
def list_need_contacts(
    need_id: uuid.UUID,
    user: User = Depends(family_user),
    db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id)

    contacts = db.scalars(
        select(ContactAttempt)
        .where(ContactAttempt.need_id == need.id)
        .order_by(ContactAttempt.attempted_at.desc())
    ).all()

    return [_contact_out(db, contact) for contact in contacts]


@router.get(
    "/families/{family_id}/contact-attempts",
    response_model=list[ContactAttemptOut],
)
def list_family_contacts(
    family_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user),
    db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id)

    statement = (
        select(ContactAttempt)
        .join(ServiceNeed, ServiceNeed.id == ContactAttempt.need_id)
        .join(Child, Child.id == ServiceNeed.child_id)
        .where(
            Child.family_id == family.id,
            Child.deleted_at.is_(None),
        )
        .order_by(ContactAttempt.attempted_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return [
        _contact_out(db, contact)
        for contact in db.scalars(statement).all()
    ]