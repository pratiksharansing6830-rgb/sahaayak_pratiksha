from datetime import datetime, timezone

import pytest

from app.core.config import settings
from app.models import Role, ServiceCategory, VerificationStatus
from tests.helpers import (
    assess, auth_headers, create_child, create_family, create_migration, make_listing, make_user,
)

API = "/api/v1"
G = f"{API}/gov"
ENDPOINTS = ["overview", "unresolved-by-category", "destinations", "trends",
             "service-gaps", "priority", "alerts"]
EDU = ServiceCategory.EDUCATION


@pytest.fixture()
def k2(monkeypatch):
    monkeypatch.setattr(settings, "min_group_size", 2)


def _gov(client, db):
    make_user(db, "gov@example.com", Role.GOVERNMENT)
    return auth_headers(client, "gov@example.com")


def _family_to(client, db, email, district="Pune"):
    make_user(db, email)
    h = auth_headers(client, email)
    fam = create_family(client, h)
    child = create_child(client, h, fam["id"])
    client.patch(f"{API}/children/{child['id']}", headers=h, json={"education_status": "NOT_ENROLLED"})
    mig = create_migration(client, h, fam["id"], destination_district=district)
    needs = {n["category"]: n for n in assess(client, h, mig["id"])["needs"]}
    return h, fam, mig, needs


def test_only_government_can_use_gov_api(client, db):
    citizen = _family_to(client, db, "c1@example.com")[0]
    make_user(db, "adm@example.com", Role.ADMIN)
    make_user(db, "sch@example.com", Role.SCHOOL)
    others = [citizen, auth_headers(client, "adm@example.com"), auth_headers(client, "sch@example.com")]
    gov = _gov(client, db)
    for ep in ENDPOINTS:
        assert client.get(f"{G}/{ep}").status_code == 401, ep
        for h in others:
            assert client.get(f"{G}/{ep}", headers=h).status_code == 403, ep
        assert client.get(f"{G}/{ep}", headers=gov).status_code == 200, ep


def test_small_numbers_are_hidden_by_default(client, db, monkeypatch):
    monkeypatch.setattr(settings, "min_group_size", 5)
    _family_to(client, db, "a@example.com")
    gov = _gov(client, db)
    o = client.get(f"{G}/overview", headers=gov).json()
    assert o["privacy"]["min_group_size"] == 5
    assert o["families_registered"] is None and o["children_registered"] is None
    assert o["children_with_open_needs"] is None and o["open_needs"] is None
    assert o["migrations_by_status"]["PLANNED"] is None
    for ep in ("unresolved-by-category", "destinations", "service-gaps", "priority"):
        assert client.get(f"{G}/{ep}", headers=gov).json()["rows"] == [], ep
    assert client.get(f"{G}/alerts", headers=gov).json()["alerts"] == []
    assert "Pune" not in client.get(f"{G}/destinations", headers=gov).text


def test_figures_appear_once_groups_are_large_enough_and_hold_no_personal_data(client, db, k2):
    _family_to(client, db, "a@example.com")
    _family_to(client, db, "b@example.com")
    gov = _gov(client, db)
    o = client.get(f"{G}/overview", headers=gov).json()
    assert o["families_registered"] == 2 and o["children_registered"] == 2
    assert o["migrations_by_status"]["PLANNED"] == 2
    assert o["children_with_open_needs"] == 2 and o["open_needs"] == 12
    assert o["children_support_confirmed_by_provider"] == 0

    cat = client.get(f"{G}/unresolved-by-category", headers=gov)
    rows = cat.json()["rows"]
    assert len(rows) == 6 and all(r["children_with_open_needs"] == 2 for r in rows)
    dest = client.get(f"{G}/destinations", headers=gov)
    assert [(r["destination_district"], r["families_moving"]) for r in dest.json()["rows"]] == [("Pune", 2)]

    blob = " ".join(client.get(f"{G}/{ep}", headers=gov).text for ep in ENDPOINTS)
    for secret in ("Asha", "Sunita", "Pawar", "Beed", "a@example.com", "b@example.com"):
        assert secret not in blob, secret


def test_destination_with_too_few_families_is_left_out(client, db, k2):
    _family_to(client, db, "a@example.com", "Pune")
    _family_to(client, db, "b@example.com", "Pune")
    _family_to(client, db, "c@example.com", "Nagpur")
    r = client.get(f"{G}/destinations", headers=_gov(client, db))
    assert [x["destination_district"] for x in r.json()["rows"]] == ["Pune"]
    assert r.json()["groups_hidden"] == 1 and "Nagpur" not in r.text


def test_family_reports_are_not_counted_as_provider_confirmation(client, db, k2):
    fams = [_family_to(client, db, f"f{i}@example.com") for i in range(3)]
    for h, fam, mig, needs in fams[:2]:
        r = client.post(f"{API}/needs/{needs['EDUCATION']['id']}/confirm", headers=h,
                        json={"outcome": "Admitted", "method": "FAMILY_REPORTED"})
        assert r.status_code == 200
    gov = _gov(client, db)
    o = client.get(f"{G}/overview", headers=gov).json()
    assert o["children_support_confirmed_by_family_only"] == 2
    assert o["children_support_confirmed_by_provider"] == 0
    assert o["confirmation_rate"]["rate_percent"] is None
    rows = {r["category"]: r for r in client.get(f"{G}/unresolved-by-category", headers=gov).json()["rows"]}
    assert "EDUCATION" not in rows                     # only one child still open: hidden
    assert rows["HEALTHCARE"]["children_with_open_needs"] == 3


def test_cancelled_moves_are_not_counted_as_demand(client, db, k2):
    _family_to(client, db, "a@example.com")
    b = _family_to(client, db, "b@example.com")
    assert client.post(f"{API}/migrations/{b[2]['id']}/status", headers=b[0],
                       json={"status": "CANCELLED"}).status_code == 200
    gov = _gov(client, db)
    d = client.get(f"{G}/destinations", headers=gov).json()
    assert d["rows"] == [] and d["groups_hidden"] == 1
    assert client.get(f"{G}/unresolved-by-category", headers=gov).json()["rows"] == []


def test_gaps_use_real_listings_only(client, db, k2):
    _family_to(client, db, "a@example.com")
    _family_to(client, db, "b@example.com")
    make_listing(db, "[SAMPLE] School", EDU, "Pune", verification_status=VerificationStatus.SAMPLE)
    gov = _gov(client, db)

    def edu_row():
        rows = client.get(f"{G}/service-gaps", headers=gov).json()["rows"]
        return next(r for r in rows if r["category"] == "EDUCATION")

    r = edu_row()
    assert r["coverage"] == "NONE" and r["potential_gap"] is True and r["directory_listings"] == 0
    make_listing(db, "Real School", EDU, "Pune", verification_status=VerificationStatus.UNVERIFIED)
    r = edu_row()
    assert r["coverage"] == "SOME" and r["potential_gap"] is False
    assert r["directory_listings"] == 1 and r["verified_listings"] == 0


def test_alerts_explain_themselves(client, db, k2):
    _family_to(client, db, "a@example.com")
    _family_to(client, db, "b@example.com")
    alerts = client.get(f"{G}/alerts", headers=_gov(client, db)).json()["alerts"]
    by = {(a["code"], a["category"]): a for a in alerts}
    a = by[("OPEN_DEMAND_UPCOMING", "EDUCATION")]
    assert a["destination_district"] == "Pune" and a["children_count"] == 2
    assert ("DIRECTORY_COVERAGE", "EDUCATION") in by
    for x in alerts:
        assert x["basis"] == "RULE_BASED"
        assert x["observation"] and x["limitations"] and x["suggested_action"] and x["window"]


def test_priority_scores_list_their_factors(client, db, k2):
    _family_to(client, db, "a@example.com")
    _family_to(client, db, "b@example.com")
    body = client.get(f"{G}/priority", headers=_gov(client, db)).json()
    assert body["rows"] and "individual" in body["disclaimer"].lower()
    names = {"Children waiting", "Overdue", "Time open",
             "Provider declined or did not respond", "Move approaching", "Directory coverage"}
    for r in body["rows"]:
        assert r["band"] in ("LOW", "MEDIUM", "HIGH")
        assert {f["name"] for f in r["factors"]} == names
        assert abs(sum(f["points"] for f in r["factors"]) - r["score"]) < 0.11


def test_trends_cover_requested_months(client, db, k2):
    _family_to(client, db, "a@example.com")
    _family_to(client, db, "b@example.com")
    pts = client.get(f"{G}/trends?months=6", headers=_gov(client, db)).json()["points"]
    assert len(pts) == 6
    assert pts[-1]["month"] == datetime.now(timezone.utc).strftime("%Y-%m")
    assert pts[-1]["new_families"] == 2 and pts[-1]["families_with_new_migrations"] == 2
    assert all(p["new_families"] == 0 for p in pts[:-1])


def test_filters_and_validation(client, db, k2):
    _family_to(client, db, "a@example.com")
    _family_to(client, db, "b@example.com")
    gov = _gov(client, db)
    url = f"{G}/unresolved-by-category"
    assert len(client.get(f"{url}?district=pune", headers=gov).json()["rows"]) == 6
    assert client.get(f"{url}?district=Nagpur", headers=gov).json()["rows"] == []
    assert len(client.get(f"{url}?category=EDUCATION", headers=gov).json()["rows"]) == 1
    assert client.get(f"{url}?from_date=2099-01-01", headers=gov).json()["rows"] == []
    r = client.get(f"{url}?district=Atlantis", headers=gov)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "LOCATION_NOT_RECOGNISED"
    assert client.get(f"{G}/overview?from_date=2026-02-01&to_date=2026-01-01", headers=gov).status_code == 422
    assert client.get(f"{url}?category=BOGUS", headers=gov).status_code == 422