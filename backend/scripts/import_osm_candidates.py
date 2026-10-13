"""Extract and import explicitly tagged Maharashtra POIs from an OSM PBF.

First create an extract with --pbf, --boundary and --output. Review the summary,
then import that JSONL using --input-jsonl and --apply. Imported entries remain
unverified. OSM contact details are never copied.
"""

import argparse
import json
from collections import Counter
from pathlib import Path

import osmium
from shapely.geometry import Point, Polygon, shape

from app.core.database import SessionLocal, engine
from app.models import ServiceCategory, ServiceListing, VerificationStatus
from app.services.locations import resolve_district

OSM_COPYRIGHT = "© OpenStreetMap contributors"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
OSM_SNAPSHOT_DATE = "2026-10-12"
REQUIRED_DISTRICT_TAGS = ("addr:district", "addr:city", "is_in:district")
NOT_ACTIVE_TAGS = ("abandoned", "disused", "construction", "proposed")


def category_evidence(tags) -> dict[ServiceCategory, str]:
    values = dict(tags)
    found: dict[ServiceCategory, str] = {}

    if values.get("amenity") == "school":
        found[ServiceCategory.EDUCATION] = "amenity=school"
    if (
        values.get("amenity") in {"hospital", "clinic"}
        or values.get("healthcare") in {"hospital", "clinic"}
    ):
        evidence = [
            f"{key}={values[key]}"
            for key in ("amenity", "healthcare")
            if values.get(key) in {"hospital", "clinic"}
        ]
        found[ServiceCategory.HEALTHCARE] = "; ".join(evidence)
    if values.get("amenity") == "anganwadi":
        found[ServiceCategory.NUTRITION] = "amenity=anganwadi"

    specialties = {
        item.strip()
        for item in values.get("healthcare:speciality", "").replace(",", ";").split(";")
    }
    mental_health = values.get("healthcare") == "psychotherapist"
    specialist_place = (
        (
            values.get("amenity") in {"hospital", "clinic", "doctors"}
            or values.get("healthcare") in {"hospital", "clinic"}
        )
        and bool(specialties & {"psychiatry", "child_psychiatry"})
    )
    if mental_health or specialist_place:
        evidence = ["healthcare=psychotherapist"] if mental_health else []
        evidence.extend(
            f"healthcare:speciality={specialty}"
            for specialty in sorted(specialties & {"psychiatry", "child_psychiatry"})
        )
        found[ServiceCategory.WELLBEING] = "; ".join(evidence)
    return found


def district_for(tags):
    for key in REQUIRED_DISTRICT_TAGS:
        value = tags.get(key)
        if value:
            district = resolve_district(value.removesuffix(" District").strip())
            if district:
                return district
    return None


def address_for(tags) -> str | None:
    if tags.get("addr:full"):
        return tags["addr:full"][:300]
    parts = [
        " ".join(filter(None, (tags.get("addr:housenumber"), tags.get("addr:street")))),
        tags.get("addr:suburb"),
        tags.get("addr:city"),
        tags.get("addr:postcode"),
    ]
    address = ", ".join(part.strip() for part in parts if part and part.strip())
    return address[:300] or None


class CandidateExtractor(osmium.SimpleHandler):
    def __init__(self, boundary, output: Path):
        super().__init__()
        self.boundary = boundary
        self.output = output.open("w", encoding="utf-8", newline="\n")
        self.counts: Counter[str] = Counter()

    def close(self):
        self.output.close()

    def node(self, obj):
        if not category_evidence(obj.tags):
            return
        point = Point(obj.location.lon, obj.location.lat) if obj.location.valid() else None
        self._write(obj, point, "node")

    def way(self, obj):
        tags = dict(obj.tags)
        if not category_evidence(tags):
            return
        coords = [(node.lon, node.lat) for node in obj.nodes if node.location.valid()]
        if len(coords) < 2:
            self.counts["missing_geometry"] += 1
            return
        if len(coords) >= 4 and coords[0] == coords[-1]:
            point = Polygon(coords).representative_point()
        else:
            point = Point(coords[len(coords) // 2])
        self._write(obj, point, "way")

    def _write(self, obj, location, osm_type: str):
        self.counts[f"{osm_type}_records_seen"] += 1
        tags = dict(obj.tags)
        evidence = category_evidence(tags)
        if not evidence:
            return
        if any(tags.get(key) in {"yes", "true"} for key in NOT_ACTIVE_TAGS):
            self.counts["inactive_or_proposed"] += 1
            return
        name = tags.get("name", "").strip()
        if not name:
            self.counts["unnamed"] += 1
            return
        district = district_for(tags)
        if district is None:
            self.counts["district_not_explicitly_mapped"] += 1
            return
        if location is None:
            self.counts["missing_geometry"] += 1
            return
        if not self.boundary.covers(location):
            self.counts["outside_boundary"] += 1
            return

        element_id = f"{osm_type}/{obj.id}"
        source = (
            f"{OSM_COPYRIGHT} (ODbL 1.0; extract {OSM_SNAPSHOT_DATE}): "
            f"https://www.openstreetmap.org/{element_id}"
        )
        address = address_for(tags)
        for category, tag_text in evidence.items():
            record = {
                "osm_id": element_id,
                "category": category.value,
                "name": name[:200],
                "description": (
                    "Unverified community-mapped candidate. "
                    f"OpenStreetMap tags: {tag_text}."
                ),
                "address": address,
                "district": district.district,
                "latitude": location.y,
                "longitude": location.x,
                "data_source": source,
            }
            self.output.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.counts[f"candidates_{category.value}"] += 1


def extract(pbf: Path, boundary_json: Path, output: Path) -> Counter[str]:
    response = json.loads(boundary_json.read_text(encoding="utf-8"))
    matches = [
        item for item in response
        if item.get("osm_type") == "relation"
        and item.get("osm_id") == 1950884
        and item.get("name") == "Maharashtra"
    ]
    if len(matches) != 1 or not matches[0].get("geojson"):
        raise ValueError("Boundary file must contain the Maharashtra OSM boundary relation 1950884.")

    extractor = CandidateExtractor(shape(matches[0]["geojson"]), output)
    try:
        extractor.apply_file(str(pbf), locations=True, idx="sparse_file_array")
    finally:
        extractor.close()
    return extractor.counts


def import_jsonl(source: Path, apply: bool) -> Counter[str]:
    counts: Counter[str] = Counter()
    with source.open("r", encoding="utf-8") as records:
        with SessionLocal() as db:
            existing_sources = {
                data_source
                for (data_source,) in db.query(ServiceListing.data_source).filter(
                    ServiceListing.data_source.is_not(None)
                )
            }
            existing_names = {
                (name.casefold(), district.casefold(), (address or "").casefold())
                for name, district, address in db.query(
                    ServiceListing.name, ServiceListing.district, ServiceListing.address
                )
            }
            pending: list[ServiceListing] = []
            for line in records:
                counts["records_read"] += 1
                item = json.loads(line)
                data_source = item["data_source"].replace(
                    " (ODbL 1.0):",
                    f" (ODbL 1.0; extract {OSM_SNAPSHOT_DATE}):",
                )
                source_key = f"{data_source} [{item['category']}]"
                name_key = (
                    item["name"].casefold(),
                    item["district"].casefold(),
                    (item["address"] or "").casefold(),
                )
                if source_key in existing_sources or (
                    item["address"] and name_key in existing_names
                ):
                    counts["duplicates"] += 1
                    continue
                existing_sources.add(source_key)
                if item["address"]:
                    existing_names.add(name_key)
                pending.append(ServiceListing(
                    name=item["name"],
                    category=ServiceCategory(item["category"]),
                    description=item["description"],
                    address=item["address"],
                    district=item["district"],
                    state="Maharashtra",
                    latitude=item["latitude"],
                    longitude=item["longitude"],
                    coordinates_approximate=True,
                    data_source=source_key[:200],
                    verification_status=VerificationStatus.UNVERIFIED,
                ))
            counts["would_add"] = len(pending)
            if apply and pending:
                db.add_all(pending)
                db.commit()
                counts["added"] = len(pending)
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, help="India OSM PBF; required for extract mode")
    parser.add_argument("--boundary", type=Path, help="Nominatim Maharashtra boundary JSON")
    parser.add_argument("--output", type=Path, help="JSONL path for extracted candidates")
    parser.add_argument("--input-jsonl", type=Path, help="Previously extracted candidates")
    parser.add_argument("--apply", action="store_true", help="Write imported candidates to the database")
    args = parser.parse_args()

    if args.input_jsonl:
        if args.pbf or args.boundary or args.output:
            parser.error("--input-jsonl cannot be combined with extraction arguments")
        print("Database:", engine.url.render_as_string(hide_password=True))
        counts = import_jsonl(args.input_jsonl, args.apply)
    else:
        if not args.pbf or not args.boundary or not args.output:
            parser.error("extract mode requires --pbf, --boundary, and --output")
        counts = extract(args.pbf, args.boundary, args.output)
        print(f"Extracted candidates: {args.output}")
        print(f"Attribution: {OSM_COPYRIGHT}; ODbL 1.0: {OSM_COPYRIGHT_URL}")
    for key, value in sorted(counts.items()):
        print(f"{key}: {value}")
    if args.input_jsonl:
        print("Mode:", "applied" if args.apply else "dry run; pass --apply to import")


if __name__ == "__main__":
    main()
