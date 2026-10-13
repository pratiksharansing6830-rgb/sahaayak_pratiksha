from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import case, exists, extract, func, literal_column, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Child, Family, FollowUp, Migration, MigrationStatus, NeedStatus, OutcomeConfirmation,
    Referral, ReferralStatus, ServiceCategory, ServiceListing, ServiceNeed, VerificationStatus,
)
from app.schemas.gov import (
    Alert, AlertsResponse, CategoryResponse, CategoryRow, ConfirmationRate, DestinationResponse,
    DestinationRow, FiltersOut, GapResponse, GapRow, Overview, PriorityFactor, PriorityResponse,
    PriorityRow, TrendPoint, TrendResponse, privacy_info,
)
from app.services.continuity import ACTIVE_FOLLOWUP, OPEN_STATUSES

OPEN = list(OPEN_STATUSES)
ACTIVE_FU = list(ACTIVE_FOLLOWUP)
CH = func.count(func.distinct(ServiceNeed.child_id))  # distinct children
GAP_RATIO = 10  # open children per directory listing at which coverage is called LOW

LABEL = {
    ServiceCategory.EDUCATION: "education",
    ServiceCategory.HEALTHCARE: "healthcare",
    ServiceCategory.NUTRITION: "nutrition",
    ServiceCategory.WELLBEING: "wellbeing",
    ServiceCategory.PROTECTION: "child protection",
    ServiceCategory.INCLUSION: "disability and inclusion",
}


@dataclass
class Filters:
    from_date: date | None = None
    to_date: date | None = None
    district: str | None = None
    category: ServiceCategory | None = None


def _fo(f: Filters) -> FiltersOut:
    return FiltersOut(from_date=f.from_date, to_date=f.to_date, district=f.district, category=f.category)


# ---------- privacy helpers ----------
def k() -> int:
    return settings.min_group_size


def cell(n: int) -> int | None:
    """Hide small non-zero figures. Zero is safe to show."""
    return None if 0 < n < k() else n


def visible(n: int) -> bool:
    return n >= k()


def _distinct_if(cond):
    return func.count(func.distinct(case((cond, ServiceNeed.child_id))))


# ---------- query helpers ----------
def _start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _end(d: date) -> datetime:
    return datetime.combine(d + timedelta(days=1), time.min, tzinfo=timezone.utc)


def _dates(stmt, col, f: Filters):
    if f.from_date:
        stmt = stmt.where(col >= _start(f.from_date))
    if f.to_date:
        stmt = stmt.where(col < _end(f.to_date))
    return stmt


def _need_stmt(f: Filters, *cols, open_only=True, followup=False, referral_join=False):
    """Needs of live families on moves that are not cancelled."""
    stmt = (
        select(*cols).select_from(ServiceNeed)
        .join(Child, Child.id == ServiceNeed.child_id)
        .join(Family, Family.id == Child.family_id)
        .join(Migration, Migration.id == ServiceNeed.migration_id)
        .where(
            Child.deleted_at.is_(None), Family.deleted_at.is_(None),
            Migration.status != MigrationStatus.CANCELLED,
        )
    )
    if open_only:
        stmt = stmt.where(ServiceNeed.status.in_(OPEN))
    if followup:
        stmt = stmt.join(FollowUp, FollowUp.need_id == ServiceNeed.id).where(FollowUp.status.in_(ACTIVE_FU))
    if referral_join:
        stmt = stmt.join(Referral, Referral.need_id == ServiceNeed.id)
    if f.category:
        stmt = stmt.where(ServiceNeed.category == f.category)
    if f.district:
        stmt = stmt.where(Migration.destination_district == f.district)
    return _dates(stmt, ServiceNeed.created_at, f)


def _children_by_area(db: Session, f: Filters, *conds, followup=False, referral_join=False) -> dict:
    stmt = _need_stmt(
        f, Migration.destination_district, ServiceNeed.category, CH,
        followup=followup, referral_join=referral_join,
    )
    if conds:
        stmt = stmt.where(*conds)
    stmt = stmt.group_by(Migration.destination_district, ServiceNeed.category)
    return {(d, c): n for d, c, n in db.execute(stmt).all()}


def _listing_counts(db: Session) -> dict:
    """Real directory entries only: active, and never SAMPLE."""
    rows = db.execute(
        select(
            ServiceListing.district, ServiceListing.category, func.count(ServiceListing.id),
            func.count(case((ServiceListing.verification_status == VerificationStatus.VERIFIED, 1))),
        )
        .where(ServiceListing.is_active.is_(True),
               ServiceListing.verification_status != VerificationStatus.SAMPLE)
        .group_by(ServiceListing.district, ServiceListing.category)
    ).all()
    return {(d, c): (t, v) for d, c, t, v in rows}


def _coverage(children: int, total: int) -> str:
    if total == 0:
        return "NONE"
    return "LOW" if children / total >= GAP_RATIO else "SOME"


def _sorted_items(d: dict):
    return sorted(d.items(), key=lambda kv: (kv[0][0], kv[0][1].value))


# ---------- 1. Overview ----------
def overview(db: Session, f: Filters) -> Overview:
    today = date.today()
    fam = db.scalar(_dates(
        select(func.count(Family.id)).where(Family.deleted_at.is_(None)), Family.created_at, f)) or 0
    kids = db.scalar(_dates(
        select(func.count(Child.id)).select_from(Child)
        .join(Family, Family.id == Child.family_id)
        .where(Child.deleted_at.is_(None), Family.deleted_at.is_(None)), Child.created_at, f)) or 0

    by_status = {s.value: 0 for s in MigrationStatus}
    rows = db.execute(_dates(
        select(Migration.status, func.count(func.distinct(Migration.family_id)))
        .select_from(Migration).join(Family, Family.id == Migration.family_id)
        .where(Family.deleted_at.is_(None)).group_by(Migration.status), Migration.created_at, f)).all()
    for s, n in rows:
        by_status[s.value] = n

    open_children, open_needs = db.execute(_need_stmt(f, CH, func.count(ServiceNeed.id))).one()
    overdue_needs = db.scalar(_need_stmt(f, CH).where(ServiceNeed.due_date < today)) or 0
    fu_over = db.scalar(_need_stmt(f, CH, followup=True).where(FollowUp.due_date < today)) or 0
    fu_due = db.scalar(_need_stmt(f, CH, followup=True).where(FollowUp.due_date >= today)) or 0

    has_pc = exists().where(OutcomeConfirmation.need_id == ServiceNeed.id,
                            OutcomeConfirmation.provider_verified.is_(True))
    has_ref = exists().where(Referral.need_id == ServiceNeed.id)
    prov = db.scalar(_need_stmt(f, CH, open_only=False).where(has_pc)) or 0
    fam_only = db.scalar(_need_stmt(f, CH, open_only=False).where(
        ServiceNeed.status == NeedStatus.SUPPORT_CONFIRMED, ~has_pc)) or 0
    with_ref = db.scalar(_need_stmt(f, CH, open_only=False).where(has_ref)) or 0
    ref_conf = db.scalar(_need_stmt(f, CH, open_only=False).where(has_ref, has_pc)) or 0

    rate_ok = visible(with_ref) and (ref_conf == 0 or visible(ref_conf)) and (
        with_ref - ref_conf == 0 or visible(with_ref - ref_conf))
    rate = ConfirmationRate(
        children_with_referral=cell(with_ref),
        children_provider_confirmed=cell(ref_conf) if rate_ok else None,
        rate_percent=round(100 * ref_conf / with_ref, 1) if rate_ok else None,
        note=(
            "Share of children with at least one referral whose support a provider has confirmed."
            if rate_ok else
            f"Not enough data to show a rate safely (needs groups of at least {k()})."
        ),
    )
    show_open = visible(open_children)
    return Overview(
        privacy=privacy_info(), generated_on=today, filters=_fo(f),
        families_registered=cell(fam), children_registered=cell(kids),
        migrations_by_status={key: cell(v) for key, v in by_status.items()},
        children_with_open_needs=cell(open_children),
        open_needs=open_needs if show_open else None,
        children_with_overdue_needs=cell(overdue_needs),
        children_with_overdue_followups=cell(fu_over),
        children_with_followups_due=cell(fu_due),
        children_support_confirmed_by_provider=cell(prov),
        children_support_confirmed_by_family_only=cell(fam_only),
        confirmation_rate=rate,
        notes=[
            "Needs on cancelled moves are not counted.",
            "Support reported only by a family is counted separately from provider-confirmed support.",
            "Only date filters apply to this overview.",
        ],
    )


# ---------- 2. Unresolved needs by category ----------
def unresolved_by_category(db: Session, f: Filters) -> CategoryResponse:
    today = date.today()
    in_flight = [NeedStatus.REFERRED, NeedStatus.AWAITING_PROVIDER_RESPONSE]
    stmt = _need_stmt(
        f, ServiceNeed.category, CH, func.count(ServiceNeed.id),
        _distinct_if(ServiceNeed.due_date < today),
        _distinct_if(ServiceNeed.status.in_(in_flight)),
    ).group_by(ServiceNeed.category)
    data = db.execute(stmt).all()
    shown = [
        CategoryRow(category=c, children_with_open_needs=ch, open_needs=n,
                    children_overdue=cell(od), children_awaiting_provider=cell(aw))
        for c, ch, n, od, aw in data if visible(ch)
    ]
    shown.sort(key=lambda r: -r.children_with_open_needs)
    return CategoryResponse(
        privacy=privacy_info(), filters=_fo(f), rows=shown, groups_hidden=len(data) - len(shown),
        note="Open needs are needs that are not yet confirmed, closed or marked not required.",
    )


# ---------- 3. Destinations ----------
def destinations(db: Session, f: Filters) -> DestinationResponse:
    def fam_if(status):
        return func.count(func.distinct(case((Migration.status == status, Migration.family_id))))

    stmt = (
        select(
            Migration.destination_district, func.count(func.distinct(Migration.family_id)),
            fam_if(MigrationStatus.PLANNED), fam_if(MigrationStatus.ACTIVE),
            fam_if(MigrationStatus.COMPLETED),
        )
        .select_from(Migration).join(Family, Family.id == Migration.family_id)
        .where(Family.deleted_at.is_(None), Migration.status != MigrationStatus.CANCELLED)
    )
    if f.district:
        stmt = stmt.where(Migration.destination_district == f.district)
    stmt = _dates(stmt, Migration.created_at, f).group_by(Migration.destination_district)
    data = db.execute(stmt).all()

    open_by_dest = {
        d: n for d, n in db.execute(
            _need_stmt(f, Migration.destination_district, CH).group_by(Migration.destination_district)
        ).all()
    }
    shown = [
        DestinationRow(
            destination_district=d, families_moving=fam, planned=cell(p), active=cell(a),
            completed=cell(c), children_with_open_needs=cell(open_by_dest.get(d, 0)),
        )
        for d, fam, p, a, c in data if visible(fam)
    ]
    shown.sort(key=lambda r: -r.families_moving)
    return DestinationResponse(
        privacy=privacy_info(), filters=_fo(f), rows=shown, groups_hidden=len(data) - len(shown),
        note="Counts families with a planned, active or completed move. Cancelled moves are not counted.",
    )


# ---------- 4. Trends ----------
def _months(n: int) -> list[tuple[int, int]]:
    now = datetime.now(timezone.utc)
    y, m, out = now.year, now.month, []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def trends(db: Session, months: int) -> TrendResponse:
    spans = _months(months)
    start = datetime(spans[0][0], spans[0][1], 1, tzinfo=timezone.utc)
    month = literal_column("'month'")

    m1 = func.date_trunc(month, Family.created_at)
    fam = {r[0].strftime("%Y-%m"): r[1] for r in db.execute(
        select(m1, func.count(Family.id))
        .where(Family.deleted_at.is_(None), Family.created_at >= start).group_by(m1)).all()}

    m2 = func.date_trunc(month, Migration.created_at)
    mig = {r[0].strftime("%Y-%m"): r[1] for r in db.execute(
        select(m2, func.count(func.distinct(Migration.family_id))).select_from(Migration)
        .join(Family, Family.id == Migration.family_id)
        .where(Family.deleted_at.is_(None), Migration.created_at >= start).group_by(m2)).all()}

    m3 = func.date_trunc(month, OutcomeConfirmation.confirmed_at)
    conf = {r[0].strftime("%Y-%m"): r[1] for r in db.execute(
        select(m3, func.count(func.distinct(Child.id))).select_from(OutcomeConfirmation)
        .join(ServiceNeed, ServiceNeed.id == OutcomeConfirmation.need_id)
        .join(Child, Child.id == ServiceNeed.child_id)
        .join(Family, Family.id == Child.family_id)
        .where(OutcomeConfirmation.provider_verified.is_(True), Child.deleted_at.is_(None),
               Family.deleted_at.is_(None), OutcomeConfirmation.confirmed_at >= start)
        .group_by(m3)).all()}

    points = []
    for y, m in spans:
        key = f"{y:04d}-{m:02d}"
        points.append(TrendPoint(
            month=key, new_families=cell(fam.get(key, 0)),
            families_with_new_migrations=cell(mig.get(key, 0)),
            children_with_provider_confirmed_outcomes=cell(conf.get(key, 0)),
        ))
    return TrendResponse(
        privacy=privacy_info(), points=points,
        note="Months are UTC. Figures are based on when records were created in Sahaayak.",
    )


# ---------- 5. Service gaps ----------
def service_gaps(db: Session, f: Filters) -> GapResponse:
    open_children = _children_by_area(db, f)
    listings = _listing_counts(db)
    rows = []
    for (d, c), ch in _sorted_items(open_children):
        if not visible(ch):
            continue
        total, verified = listings.get((d, c), (0, 0))
        cov = _coverage(ch, total)
        if cov == "NONE":
            why = f"{ch} children have an open {LABEL[c]} need, and Sahaayak's directory has no {LABEL[c]} service in {d}."
        elif cov == "LOW":
            why = f"{ch} children have an open {LABEL[c]} need for {total} directory listing(s) in {d}."
        else:
            why = f"The directory lists {total} {LABEL[c]} service(s) in {d} for {ch} children with an open need."
        rows.append(GapRow(
            destination_district=d, category=c, children_with_open_needs=ch,
            directory_listings=total, verified_listings=verified, coverage=cov,
            potential_gap=cov in ("NONE", "LOW"), explanation=why,
        ))
    rows.sort(key=lambda r: (not r.potential_gap, -r.children_with_open_needs))
    hidden = len(open_children) - len(rows)
    return GapResponse(
        privacy=privacy_info(), filters=_fo(f), rows=rows, groups_hidden=hidden,
        note=("Coverage reflects only what is in Sahaayak's directory. It is not a measure of "
              "real-world capacity, and a thin directory may just mean listings have not been added yet."),
    )


# ---------- 6. Explainable priority ----------
def priority(db: Session, f: Filters, limit: int) -> PriorityResponse:
    today = date.today()
    soon = today + timedelta(days=14)
    ke = k()
    move = (Migration.status == MigrationStatus.ACTIVE) | (
        (Migration.status == MigrationStatus.PLANNED) & Migration.planned_date.between(today, soon))
    stmt = _need_stmt(
        f, Migration.destination_district, ServiceNeed.category, CH,
        _distinct_if(ServiceNeed.due_date < today), _distinct_if(move),
        func.avg(extract("epoch", func.now() - ServiceNeed.created_at)),
    ).group_by(Migration.destination_district, ServiceNeed.category)
    data = db.execute(stmt).all()
    nonresp = _children_by_area(
        db, f, Referral.status.in_([ReferralStatus.DECLINED, ReferralStatus.NO_RESPONSE]),
        referral_join=True)
    listings = _listing_counts(db)

    def eff(n: int) -> int:  # figures below the threshold count as zero, so scores cannot leak them
        return n if n >= ke else 0

    rows = []
    for d, c, ch, od, mv, avg_secs in data:
        if not visible(ch):
            continue
        avg_days = float(avg_secs or 0) / 86400
        total, _ = listings.get((d, c), (0, 0))
        cov = _coverage(ch, total)
        cov_pts = 10.0 if cov == "NONE" else 5.0 if cov == "LOW" else 0.0
        factors = [
            PriorityFactor(name="Children waiting", points=float(min(20, ch)), max_points=20,
                           detail=f"{ch} children have an open need (1 point each, up to 20)."),
            PriorityFactor(name="Overdue", points=round(25 * eff(od) / ch, 1), max_points=25,
                           detail=f"Share of these children with a need past its due date (counts under {ke} are treated as zero)."),
            PriorityFactor(name="Time open", points=round(min(15.0, avg_days / 3), 1), max_points=15,
                           detail=f"Needs have been open {avg_days:.0f} days on average (1 point per 3 days, up to 15)."),
            PriorityFactor(name="Provider declined or did not respond",
                           points=round(15 * eff(nonresp.get((d, c), 0)) / ch, 1), max_points=15,
                           detail=f"Share of these children with a declined or unanswered referral (counts under {ke} are treated as zero)."),
            PriorityFactor(name="Move approaching", points=round(15 * eff(mv) / ch, 1), max_points=15,
                           detail=f"Share of these children whose move is under way or planned within 14 days (counts under {ke} are treated as zero)."),
            PriorityFactor(name="Directory coverage", points=cov_pts, max_points=10,
                           detail={"NONE": "No directory listing for this service here.",
                                   "LOW": "Few directory listings for the number of children.",
                                   "SOME": "The directory has listings here."}[cov]),
        ]
        score = round(sum(p.points for p in factors), 1)
        band = "HIGH" if score >= 60 else "MEDIUM" if score >= 35 else "LOW"
        rows.append(PriorityRow(destination_district=d, category=c, score=score, band=band,
                                children_with_open_needs=ch, factors=factors))
    rows.sort(key=lambda r: -r.score)
    return PriorityResponse(
        privacy=privacy_info(), filters=_fo(f),
        disclaimer=("A rules-based aid for deciding where to look first. It says nothing about any "
                    "individual child or family and does not replace human judgement."),
        rows=rows[:limit], groups_hidden=len(data) - len([r for r in data if visible(r[2])]),
    )


# ---------- 7. Early-warning alerts ----------
def alerts(db: Session, f: Filters) -> AlertsResponse:
    now = datetime.now(timezone.utc)
    today = date.today()
    ke = k()
    listings = _listing_counts(db)
    out: list[Alert] = []

    def add(code, n, d, c, title, observation, window, limitations, action):
        out.append(Alert(
            code=code, severity="ATTENTION" if n >= 2 * ke else "WATCH", title=title,
            destination_district=d, category=c, children_count=n, observation=observation,
            window=window, limitations=limitations, suggested_action=action,
        ))

    # 1. Upcoming demand
    move = (Migration.status == MigrationStatus.ACTIVE) | (
        (Migration.status == MigrationStatus.PLANNED)
        & Migration.planned_date.between(today, today + timedelta(days=30)))
    for (d, c), n in _sorted_items(_children_by_area(db, f, move)):
        if visible(n):
            add("OPEN_DEMAND_UPCOMING", n, d, c,
                f"About {n} children may need {LABEL[c]} support in {d}",
                f"{n} children in families moving to {d} (under way, or planned within 30 days) still have an open {LABEL[c]} need.",
                "Moves under way or planned in the next 30 days",
                "Counts only families registered in Sahaayak. An open need is not a confirmed shortage.",
                f"Check local {LABEL[c]} capacity in {d} and tell the relevant offices.")

    # 2. Repeated failed referrals
    start = now - timedelta(days=30)
    failed = _children_by_area(
        db, f, Referral.status.in_([ReferralStatus.DECLINED, ReferralStatus.NO_RESPONSE]),
        Referral.referred_at >= start, referral_join=True)
    for (d, c), n in _sorted_items(failed):
        if visible(n):
            add("REPEATED_REFERRAL_FAILURES", n, d, c,
                f"Repeated unsuccessful {LABEL[c]} referrals for destination {d}",
                f"{n} children with an open {LABEL[c]} need had a referral declined or left unanswered.",
                "Referrals recorded in the last 30 days",
                "Uses the referral date, not the date of the decline. Declines can have valid reasons, such as no places.",
                "Ask the providers concerned what is blocking support and whether more capacity is needed.")

    # 3. Overdue backlog
    over = _children_by_area(db, f, FollowUp.due_date < today, followup=True)
    for (d, c), n in _sorted_items(over):
        if visible(n):
            add("OVERDUE_BACKLOG", n, d, c,
                f"Overdue {LABEL[c]} follow-ups for destination {d}",
                f"{n} children have a {LABEL[c]} follow-up that is past its due date.",
                "Current open follow-ups",
                "Follow-ups may be overdue because families lack information or contact, not only because services are slow.",
                "Consider outreach through a support worker and check whether families need help.")

    # 4. Directory coverage
    for (d, c), n in _sorted_items(_children_by_area(db, f)):
        if visible(n) and listings.get((d, c), (0, 0))[0] == 0:
            add("DIRECTORY_COVERAGE", n, d, c,
                f"No {LABEL[c]} services listed for {d}",
                f"{n} children have an open {LABEL[c]} need, but the directory has no {LABEL[c]} service in {d}.",
                "Current directory",
                "The directory may simply be incomplete. This does not mean no service exists.",
                f"Identify {LABEL[c]} services in {d}, verify them and add them to the directory.")

    # 5. Slow provider responses
    delay_stmt = (
        _need_stmt(f, ServiceListing.district, ServiceNeed.category, CH, referral_join=True)
        .join(ServiceListing, ServiceListing.id == Referral.service_listing_id)
        .where(Referral.status == ReferralStatus.RECORDED,
               Referral.referred_at < now - timedelta(days=7))
        .group_by(ServiceListing.district, ServiceNeed.category)
    )
    for d, c, n in sorted(db.execute(delay_stmt).all(), key=lambda r: (r[0], r[1].value)):
        if visible(n):
            add("PROVIDER_DELAY", n, d, c,
                f"{LABEL[c].capitalize()} providers in {d} have not answered referrals",
                f"{n} children have a {LABEL[c]} referral to a provider in {d} that has had no response for over 7 days.",
                "Referrals older than 7 days with no response",
                "A provider may not yet have an account in Sahaayak, or may respond outside it.",
                "Contact the providers and check they can see and answer their referrals.")

    out.sort(key=lambda a: (a.severity != "ATTENTION", -a.children_count))
    return AlertsResponse(
        privacy=privacy_info(), generated_on=today, filters=_fo(f), alerts=out,
        note="Alerts come from fixed rules, not a predictive model. Each one needs human review before action.",
    )