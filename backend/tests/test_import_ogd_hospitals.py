from scripts.import_ogd_hospitals import SOURCE, listing_from_row, parse_coordinates
from app.models import ServiceCategory, VerificationStatus


def _row(**changes):
    row = {
        "Hospital_Name": "District Hospital",
        "State": "Maharashtra",
        "District": "Pune",
        "Address_Original_First_Line": "Main road",
        "Location_Coordinates": "18.52, 73.86",
        "Hospital_Category": "Public/ Government",
        "Telephone": "not imported",
    }
    row.update(changes)
    return row


def test_parse_source_coordinates():
    assert parse_coordinates("18.52, 73.86") == (18.52, 73.86)
    assert parse_coordinates("NA") is None
    assert parse_coordinates("91, 73.86") is None


def test_listing_is_canonical_and_unverified_without_contact_details():
    listing, reason = listing_from_row(_row(District="Raigarh"))

    assert reason is None
    assert listing is not None
    assert listing.district == "Raigad"
    assert listing.category == ServiceCategory.HEALTHCARE
    assert listing.verification_status == VerificationStatus.UNVERIFIED
    assert listing.data_source == SOURCE
    assert listing.contact_phone is None


def test_ambiguous_district_is_skipped():
    listing, reason = listing_from_row(_row(District="Mumbai"))

    assert listing is None
    assert reason == "missing_or_unsupported_location"


def test_non_maharashtra_row_is_skipped():
    listing, reason = listing_from_row(_row(State="Gujarat"))

    assert listing is None
    assert reason == "outside_maharashtra"
