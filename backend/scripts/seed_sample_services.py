"""Add FICTIONAL sample directory entries. Run from backend/:  python -m scripts.seed_sample_services"""
from sqlalchemy import select

from app.core.database import SessionLocal, engine
from app.models import ServiceCategory, ServiceListing, VerificationStatus
from app.services.locations import DISTRICTS

LABELS = {
    ServiceCategory.EDUCATION: "School",
    ServiceCategory.HEALTHCARE: "Health Centre",
    ServiceCategory.NUTRITION: "Nutrition Centre",
    ServiceCategory.WELLBEING: "Wellbeing Service",
    ServiceCategory.PROTECTION: "Child Protection Service",
    ServiceCategory.INCLUSION: "Inclusion Support Service",
}
DEMO_DISTRICTS = ["Pune", "Nagpur"]


def main() -> None:
    print("Database:", engine.url.render_as_string(hide_password=True))
    print("This adds fictional entries marked SAMPLE. They are not real services.")
    if input("Type 'yes' to continue: ").strip().lower() != "yes":
        raise SystemExit("Cancelled. Nothing was changed.")

    added = 0
    with SessionLocal() as db:
        for district in DEMO_DISTRICTS:
            lat, lng = DISTRICTS[district]
            for i, category in enumerate(ServiceCategory):
                name = f"[SAMPLE] {LABELS[category]} - {district}"
                if db.scalar(select(ServiceListing.id).where(
                        ServiceListing.name == name, ServiceListing.district == district)):
                    continue
                db.add(ServiceListing(
                    name=name, category=category, district=district, state="Maharashtra",
                    description="Fictional demo entry. Not a real service.",
                    latitude=lat + 0.01 * i, longitude=lng + 0.01 * (i % 3),
                    coordinates_approximate=True,
                    data_source="Sahaayak demo data (fictional)",
                    verification_status=VerificationStatus.SAMPLE,
                ))
                added += 1
        db.commit()
    print(f"Added {added} sample entries.")


if __name__ == "__main__":
    main()