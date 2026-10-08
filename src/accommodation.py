"""
Accommodation listings and a total study-abroad cost estimate.

Real listings come from Geoapify's Places API when GEOAPIFY_API_KEY is
set — genuine names, addresses and distances for real accommodation
near a university's real coordinates. Geoapify does not report price,
so a price estimate is still attached to each real listing, grounded
in the university's own real housing cost where one exists and clearly
marked as an estimate rather than implied to come from Geoapify too.

Without a configured key, with no results nearby, or if the request
fails, listings fall back to clearly-labelled samples — never shown
without an "(Sample)" marker a student could mistake for a real
property, the same discipline the rest of the app applies to fees,
rankings and reviews it can't source.
"""

import hashlib
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request

GEOAPIFY_PLACES_URL = "https://api.geoapify.com/v2/places"
GEOAPIFY_GEOCODE_URL = "https://api.geoapify.com/v1/geocode/search"
SEARCH_RADIUS_METERS = 3000
REQUEST_TIMEOUT_SECONDS = 8

CATEGORY_LABELS = {
    "accommodation.hotel": "Hotel",
    "accommodation.hostel": "Hostel",
    "accommodation.guest_house": "Guest House",
    "accommodation.apartment": "Apartment",
    "accommodation.motel": "Motel",
}

SAMPLE_NAMES = [
    "Campus View Residence",
    "University Quarter Apartments",
    "Scholars Lodge",
    "Green Street Student Housing",
]

ROOM_TYPES = ["Single Room", "Shared Room", "Studio Apartment", "Shared Apartment"]

FACILITIES_POOL = [
    "WiFi", "Furnished", "Laundry", "24/7 Security", "Study Room",
    "Gym Access", "Meals Included", "Bike Storage", "Common Kitchen",
]

GENERIC_MONTHLY_FALLBACK = 700

# A reasonable, clearly-editable starting point — not a claim about any
# specific place. Food and transport scale with a country's real
# cost-of-living index where one exists; everything here is meant to be
# overwritten by the student with their own numbers.
BASELINE_FOOD_MONTHLY_USD = 450
BASELINE_TRANSPORT_MONTHLY_USD = 100
BASELINE_COST_OF_LIVING_INDEX = 70.0  # approx. US index, used as the scale's anchor

_geocode_cache: dict[str, tuple[float, float] | None] = {}


def _fraction(seed: str) -> float:
    """A stable 0..1 value derived from a seed string — deterministic,
    so the same input always shows the same price variation instead of
    reshuffling on every request."""

    digest = hashlib.sha256(seed.encode()).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _geoapify_get(url: str, params: dict):
    api_key = os.getenv("GEOAPIFY_API_KEY")

    if not api_key:
        return None

    query = urllib.parse.urlencode({**params, "apiKey": api_key})

    try:
        with urllib.request.urlopen(f"{url}?{query}", timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None


def _haversine_km(lat1, lon1, lat2, lon2):
    earth_radius_km = 6371
    p1, p2 = math.radians(lat1), math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(delta_lon / 2) ** 2
    )

    return earth_radius_km * 2 * math.asin(math.sqrt(a))


def geocode(place_text: str):
    """
    Real coordinates for a place Geoapify can resolve — used for
    sources with no stored latitude/longitude (India). Cached for the
    life of the process, since an institute's location never changes.
    """

    feature = _geocode_feature(place_text)

    if feature is None:
        return None

    lon, lat = feature["geometry"]["coordinates"]
    return lat, lon


def geocode_city(place_text: str):
    """The real city name Geoapify resolves a place to — used to find
    the nearest airport for sources with no stored city (India), since
    airport search only matches plain city names, not full institution
    names or addresses."""

    feature = _geocode_feature(place_text)
    return feature["properties"].get("city") if feature else None


def _geocode_feature(place_text: str):
    if place_text in _geocode_cache:
        return _geocode_cache[place_text]

    data = _geoapify_get(GEOAPIFY_GEOCODE_URL, {"text": place_text, "limit": 1})
    result = data["features"][0] if data and data.get("features") else None

    _geocode_cache[place_text] = result
    return result


def nearby_airport_cities(lat: float, lon: float, limit: int = 8):
    """
    Real nearby airports by geographic proximity, nearest first — used
    to find a university's actual airport when searching by its stored
    city name fails or is ambiguous. A single generous radius, not a
    progressively-widened one: a university town's own small airport
    is often not the one students actually fly through (Oxford's own
    airport has no real international fares — students fly via London,
    ~80km away), so stopping at the first, nearest match would miss
    exactly the airport that matters. bias=proximity keeps results
    ordered nearest-first even across that wider area.
    """

    data = _geoapify_get(GEOAPIFY_PLACES_URL, {
        "categories": "airport.international",
        "filter": f"circle:{lon},{lat},150000",
        "bias": f"proximity:{lon},{lat}",
        "limit": limit,
    })

    return [
        {"name": f["properties"].get("name"), "city": f["properties"].get("city")}
        for f in (data or {}).get("features", [])
        if f["properties"].get("city")
    ]


def _place_type(categories):
    for category in categories or []:
        if category in CATEGORY_LABELS:
            return CATEGORY_LABELS[category]

    return "Accommodation"


def _price_estimate(anchor: float, seed: str) -> int:
    variation = 1 + (_fraction(seed) - 0.5) * 0.5  # +/-25%
    return max(150, round(anchor * variation / 10) * 10)


def _real_listings(lat: float, lon: float, base_monthly_rent, count: int):
    data = _geoapify_get(GEOAPIFY_PLACES_URL, {
        "categories": "accommodation",
        "filter": f"circle:{lon},{lat},{SEARCH_RADIUS_METERS}",
        "bias": f"proximity:{lon},{lat}",
        "limit": count,
    })

    if not data or not data.get("features"):
        return None

    has_real_baseline = base_monthly_rent is not None and base_monthly_rent > 0
    anchor = base_monthly_rent if has_real_baseline else GENERIC_MONTHLY_FALLBACK

    listings = []

    for index, feature in enumerate(data["features"]):
        props = feature["properties"]
        name = props.get("name") or props.get("address_line1")

        if not name:
            continue

        place_lon, place_lat = feature["geometry"]["coordinates"]
        price = _price_estimate(anchor, f"{name}-{index}")

        listings.append({
            "name": name,
            "address": props.get("formatted"),
            "distance_km": round(_haversine_km(lat, lon, place_lat, place_lon), 1),
            "monthly_price": price,
            "annual_price": price * 12,
            "place_type": _place_type(props.get("categories")),
            "map_url": f"https://www.google.com/maps/search/?api=1&query={place_lat},{place_lon}",
            "is_sample": False,
            "price_is_estimated": True,
        })

    return (listings, has_real_baseline) if listings else None


def _sample_listings(key: str, base_monthly_rent, city, count: int):
    has_real_baseline = base_monthly_rent is not None and base_monthly_rent > 0
    anchor = base_monthly_rent if has_real_baseline else GENERIC_MONTHLY_FALLBACK
    search_target = f"student housing near {city}" if city else "student housing"

    listings = []

    for i in range(count):
        price = _price_estimate(anchor, f"{key}-price-{i}")
        distance_km = round(0.2 + _fraction(f"{key}-dist-{i}") * 2.3, 1)
        rating = round(3.7 + _fraction(f"{key}-rate-{i}") * 1.1, 1)

        facility_offset = int(_fraction(f"{key}-fac-{i}") * len(FACILITIES_POOL))
        facilities = [
            FACILITIES_POOL[(facility_offset + j) % len(FACILITIES_POOL)]
            for j in range(4)
        ]

        listings.append({
            "name": f"{SAMPLE_NAMES[i % len(SAMPLE_NAMES)]} (Sample)",
            "distance_km": distance_km,
            "monthly_price": price,
            "annual_price": price * 12,
            "room_type": ROOM_TYPES[i % len(ROOM_TYPES)],
            "facilities": facilities,
            "rating": rating,
            "map_url": (
                "https://www.google.com/maps/search/"
                + search_target.replace(" ", "+")
            ),
            "is_sample": True,
        })

    return listings, has_real_baseline


def get_accommodation_listings(
    key: str, lat=None, lon=None, base_monthly_rent=None, city=None, count: int = 4
):
    """
    Real Geoapify listings near (lat, lon) when available; otherwise
    clearly-labelled samples anchored to the real housing cost where
    one exists. Returns (listings, has_real_baseline, is_real_data).
    """

    if lat is not None and lon is not None:
        real = _real_listings(lat, lon, base_monthly_rent, count)

        if real is not None:
            listings, has_real_baseline = real
            return listings, has_real_baseline, True

    listings, has_real_baseline = _sample_listings(key, base_monthly_rent, city, count)
    return listings, has_real_baseline, False


def food_transport_estimate(cost_of_living_index=None):
    """
    Monthly food and transport starting points. Scaled by a country's
    real cost-of-living index when one is available (international
    programmes); otherwise the US-anchored baseline is used as-is.
    Always meant to be edited, never presented as a specific fact.
    """

    scale = (
        cost_of_living_index / BASELINE_COST_OF_LIVING_INDEX
        if cost_of_living_index else 1.0
    )

    return {
        "food_monthly": round(BASELINE_FOOD_MONTHLY_USD * scale),
        "transport_monthly": round(BASELINE_TRANSPORT_MONTHLY_USD * scale),
    }
