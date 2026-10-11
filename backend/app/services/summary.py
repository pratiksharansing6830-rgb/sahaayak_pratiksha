from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Child, Family, NeedStatus, OutcomeConfirmation, ServiceCategory, ServiceNeed
from app.schemas.continuity import (
    ConfirmationBrief, ContinuitySummary, SummaryChild, SummaryNeed, SummaryTotals, UnresolvedItem,
)
from app.services.continuity import OPEN_STATUSES, STATUS_TEXT

CATEGORY_ORDER = {c: i for i, c in enumerate(ServiceCategory)}


def build_summary(db: Session, family: Family) -> ContinuitySummary:
    today = date.today()
    children = db.scalars(
        select(Child).where(Child.family_id == family.id, Child.deleted_at.is_(None))
        .order_by(Child.created_at)
    ).all()
    child_ids = [c.id for c in children]

    needs: list[ServiceNeed] = []
    latest_confirmation: dict = {}
    if child_ids:
        needs = list(db.scalars(
            select(ServiceNeed).where(ServiceNeed.child_id.in_(child_ids)).order_by(ServiceNeed.created_at)
        ).all())
        if needs:
            rows = db.scalars(
                select(OutcomeConfirmation)
                .where(OutcomeConfirmation.need_id.in_([n.id for n in needs]))
                .order_by(OutcomeConfirmation.confirmed_at.desc())
            ).all()
            for r in rows:
                latest_confirmation.setdefault(r.need_id, r)

    open_n = overdue_n = by_provider = by_family = not_required = closed = not_assessed = 0
    summary_children: list[SummaryChild] = []
    unresolved: list[UnresolvedItem] = []

    for child in children:
        child_needs = sorted(
            (n for n in needs if n.child_id == child.id), key=lambda n: CATEGORY_ORDER[n.category]
        )
        covered = {n.category for n in child_needs}
        missing = [c for c in ServiceCategory if c not in covered]
        not_assessed += len(missing)

        items: list[SummaryNeed] = []
        for n in child_needs:
            is_open = n.status in OPEN_STATUSES
            overdue = is_open and n.due_date is not None and n.due_date < today
            why = n.status_explanation or STATUS_TEXT[n.status][0]
            conf = latest_confirmation.get(n.id) if n.status == NeedStatus.SUPPORT_CONFIRMED else None

            if is_open:
                open_n += 1
                overdue_n += 1 if overdue else 0
                unresolved.append(UnresolvedItem(
                    need_id=n.id, child_id=child.id, child_name=child.full_name, category=n.category,
                    status=n.status, need_description=n.need_description, why=why,
                    next_action=n.next_action, due_date=n.due_date, overdue=overdue,
                ))
            elif n.status == NeedStatus.SUPPORT_CONFIRMED and conf is not None:
                if conf.provider_verified:
                    by_provider += 1
                else:
                    by_family += 1
            elif n.status == NeedStatus.NOT_REQUIRED:
                not_required += 1
            elif n.status == NeedStatus.CLOSED:
                closed += 1

            items.append(SummaryNeed(
                need_id=n.id, migration_id=n.migration_id, category=n.category, status=n.status,
                is_open=is_open, explanation=why, next_action=n.next_action, due_date=n.due_date,
                overdue=overdue,
                confirmation=ConfirmationBrief(
                    method=conf.method, provider_verified=conf.provider_verified,
                    confirmed_by_role=conf.confirmed_by_role, confirmed_at=conf.confirmed_at,
                ) if conf else None,
            ))
        summary_children.append(SummaryChild(
            child_id=child.id, child_name=child.full_name, needs=items, not_assessed_categories=missing,
        ))

    unresolved.sort(key=lambda u: (not u.overdue, u.due_date or date.max))
    return ContinuitySummary(
        family_id=family.id, generated_on=today,
        totals=SummaryTotals(
            open=open_n, overdue=overdue_n, support_confirmed_by_provider=by_provider,
            support_confirmed_by_family=by_family, not_required=not_required, closed=closed,
            not_assessed=not_assessed,
        ),
        children=summary_children, unresolved=unresolved,
    )