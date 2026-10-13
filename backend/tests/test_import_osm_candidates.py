from scripts.import_osm_candidates import address_for, category_evidence, district_for
from app.models import ServiceCategory


def test_maps_only_explicit_osm_service_tags():
    tags = {
        "amenity": "hospital",
        "healthcare:speciality": "psychiatry;child_psychiatry",
    }

    categories = category_evidence(tags)

    assert categories[ServiceCategory.HEALTHCARE] == "amenity=hospital"
    assert "psychiatry" in categories[ServiceCategory.WELLBEING]
    assert ServiceCategory.NUTRITION not in categories
    assert ServiceCategory.PROTECTION not in categories
    assert ServiceCategory.INCLUSION not in categories


def test_does_not_infer_anganwadi_or_disability_support():
    assert category_evidence({"amenity": "kindergarten"}) == {}
    assert category_evidence({"wheelchair": "yes"}) == {}
    assert category_evidence({"social_facility": "group_home"}) == {}
    assert category_evidence({"amenity": "anganwadi"}) == {
        ServiceCategory.NUTRITION: "amenity=anganwadi"
    }


def test_requires_explicit_supported_district_and_builds_address():
    assert district_for({"addr:district": "Raigarh"}).district == "Raigad"
    assert district_for({"addr:city": "Mumbai"}) is None
    assert address_for({"addr:housenumber": "10", "addr:street": "Main Road"}) == "10 Main Road"
    assert address_for({}) is None
