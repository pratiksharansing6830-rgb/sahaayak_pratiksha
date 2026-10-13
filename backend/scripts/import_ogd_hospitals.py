"""Import Maharashtra hospital records from the OGD India directory CSV.

Run from backend/ with --csv pointing to a downloaded source file. The default
is a dry run; pass --apply to write records. Contact details are not imported.
"""

import argparse
import csv
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.models import ServiceCategory, ServiceListing, VerificationStatus
from app.services.locations import resolve_district

SOURCE = (
    "OGD India National Hospital Directory; catalog updated 2025-06-02: "
    "https://www.data.gov.in/resource/"
    "national-hospital-directory-geo-code-and-additional-parameters-updated-till-last-month"
)
REQUIRED_COLUMNS = {"Hospital_Name", "State", "District"}
COORDINATE_SPLIT = re.compile(r"\s*,\s*")


def parse_coordinates(value: str | None) -> tuple[float, float] | None:
    if not value or value.strip().upper() in {"", "NA", "N/A", "NULL"}:
        return None
    parts = COORDINATE_SPLIT.split(value.strip())
    if len(parts) != 2:
        return None
    try:
        latitude, longitude = (float(part) for part in parts)
    except ValueError:
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude


def listing_from_row(row: dict[str, str]) -> tuple[ServiceListing | None, str | None]:
    if row["State"].strip().casefold() != "maharashtra":
        return None, "outside_maharashtra"

    name = row["Hospital_Name"].strip()
    location = resolve_district(row["District"])
    if not name or location is None:
        return None, "missing_or_unsupported_location"

    coordinates = parse_coordinates(row.get("Location_Coordinates"))
    category_detail = row.get("Hospital_Category", "").strip()
    description = (
        f"Source category: {category_detail}"
        if category_detail and category_detail != "0"
        else None
    )
    return ServiceListing(
        name=name[:200],
        category=ServiceCategory.HEALTHCARE,
        description=description,
        address=(row.get("Address_Original_First_Line") or "").strip()[:300] or None,
        district=location.district,
        state=location.state,
        latitude=coordinates[0] if coordinates else None,
        longitude=coordinates[1] if coordinates else None,
        coordinates_approximate=True,
        data_source=SOURCE,
        verification_status=VerificationStatus.UNVERIFIED,
    ), None


def dedupe_key(name: str, district: str, address: str | None) -> tuple[str, str, str]:
    def clean(value: str | None) -> str:
        return " ".join((value or "").casefold().split())

    return clean(name), clean(district), clean(address)


def import_file(csv_path: Path, apply: bool) -> Counter[str]:
    counts: Counter[str] = Counter()
    with csv_path.open("r", encoding="utf-8-sig", newline="") as source_file:
        reader = csv.DictReader(source_file)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")

        with SessionLocal() as db:
            existing = {
                dedupe_key(name, district, address)
                for name, district, address in db.execute(
                    select(ServiceListing.name, ServiceListing.district, ServiceListing.address)
                )
            }
            pending: list[ServiceListing] = []
            for row in reader:
                counts["rows_read"] += 1
                listing, reason = listing_from_row(row)
                if reason:
                    counts[reason] += 1
                    continue
                assert listing is not None
                key = dedupe_key(listing.name, listing.district, listing.address)
                if key in existing:
                    counts["duplicates"] += 1
                    continue
                existing.add(key)
                pending.append(listing)
                counts["coordinates"] += listing.latitude is not None
                counts["without_coordinates"] += listing.latitude is None

            counts["would_add"] = len(pending)
            if apply and pending:
                db.add_all(pending)
                db.commit()
                counts["added"] = len(pending)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="Downloaded OGD hospital directory CSV")
    parser.add_argument("--apply", action="store_true", help="Write records; otherwise only show a dry run")
    args = parser.parse_args()

    print("Database:", engine.url.render_as_string(hide_password=True))
    print("Source:", SOURCE)
    print("Imported fields exclude all telephone, email, and personal-contact columns.")
    print("Listings are added as UNVERIFIED; unsupported or ambiguous districts are skipped.")
    counts = import_file(args.csv, args.apply)
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")
    print("Mode:", "applied" if args.apply else "dry run; pass --apply to import")


if __name__ == "__main__":
    main()
