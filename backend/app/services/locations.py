import difflib
import math
import re
from typing import NamedTuple

from fastapi import HTTPException

STATE = "Maharashtra"

# Approximate district centres (lat, lng). Used only for rough distance and map centring.
DISTRICTS: dict[str, tuple[float, float]] = {
    "Ahilyanagar": (19.09, 74.74), "Akola": (20.71, 77.00), "Amravati": (20.93, 77.75),
    "Beed": (18.99, 75.76), "Bhandara": (21.17, 79.65), "Buldhana": (20.53, 76.18),
    "Chandrapur": (19.96, 79.30), "Chhatrapati Sambhajinagar": (19.88, 75.34),
    "Dhule": (20.90, 74.77), "Dharashiv": (18.18, 76.04), "Gadchiroli": (20.18, 80.00),
    "Gondia": (21.46, 80.19), "Hingoli": (19.72, 77.15), "Jalgaon": (21.00, 75.57),
    "Jalna": (19.84, 75.88), "Kolhapur": (16.70, 74.24), "Latur": (18.40, 76.58),
    "Mumbai City": (18.97, 72.83), "Mumbai Suburban": (19.08, 72.88),
    "Nagpur": (21.15, 79.09), "Nanded": (19.16, 77.31), "Nandurbar": (21.37, 74.24),
    "Nashik": (20.00, 73.79), "Palghar": (19.70, 72.77), "Parbhani": (19.27, 76.77),
    "Pune": (18.52, 73.86), "Raigad": (18.52, 73.18), "Ratnagiri": (16.99, 73.30),
    "Sangli": (16.85, 74.58), "Satara": (17.68, 74.00), "Sindhudurg": (16.35, 73.75),
    "Solapur": (17.66, 75.91), "Thane": (19.22, 72.98), "Wardha": (20.75, 78.60),
    "Washim": (20.11, 77.13), "Yavatmal": (20.39, 78.12),
}
ALIASES = {
    "ahmednagar": "Ahilyanagar",
    "aurangabad": "Chhatrapati Sambhajinagar",
    "sambhajinagar": "Chhatrapati Sambhajinagar",
    "osmanabad": "Dharashiv",
    "raigarh": "Raigad",
}


class Location(NamedTuple):
    district: str
    state: str
    latitude: float
    longitude: float


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


_LOOKUP: dict[str, str] = {normalize(k): k for k in DISTRICTS}
_LOOKUP.update({normalize(a): c for a, c in ALIASES.items()})


def resolve_district(name: str) -> Location | None:
    canonical = _LOOKUP.get(normalize(name))
    if canonical is None:
        return None
    lat, lng = DISTRICTS[canonical]
    return Location(canonical, STATE, lat, lng)


def suggest(name: str) -> list[str]:
    n = normalize(name)
    keys = list(_LOOKUP)
    found: list[str] = []
    if len(n) >= 3:
        found += [_LOOKUP[k] for k in keys if k.startswith(n) or n in k]
    found += [_LOOKUP[k] for k in difflib.get_close_matches(n, keys, n=3, cutoff=0.7)]
    out: list[str] = []
    for item in found:
        if item not in out:
            out.append(item)
    return out[:5]


def require_location(district: str, state: str | None) -> Location:
    """Resolve a district or refuse. Never falls back to a default place."""
    if state and normalize(state) != normalize(STATE):
        raise HTTPException(422, {
            "code": "STATE_NOT_SUPPORTED",
            "message": f"Sahaayak currently supports {STATE} only.",
            "suggestions": [],
        })
    loc = resolve_district(district)
    if loc is None:
        raise HTTPException(422, {
            "code": "LOCATION_NOT_RECOGNISED",
            "message": (
                f"We do not recognise '{district.strip()}' as a {STATE} district. "
                "Please check the spelling or choose one of the suggestions."
            ),
            "suggestions": suggest(district),
        })
    return loc


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))