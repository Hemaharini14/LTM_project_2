"""
Real round-trip flight prices via the Ignav Flight API.

Unlike accommodation, there is no honest "generic estimate" fallback
here — flight prices vary too much by route, season, and booking
window to approximate, which is exactly why the flight-cost field in
the cost calculator was left at 0 with no default. This module exists
to replace that blank with a real, searched price when a student
provides a real origin and real travel dates; it never invents a
figure when the search itself fails or isn't configured.
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

IGNAV_BASE_URL = "https://ignav.com/api"
REQUEST_TIMEOUT_SECONDS = 20

# Ignav's airport search matches a bare city name only — "Cambridge,
# MA" returns nothing, but a bare "Cambridge" matches both Cambridge,
# MA and Cambridge, UK, with no guarantee which comes first. A real
# city name collision was found this way: MIT (Cambridge, MA) resolved
# to Cambridge Airport in the UK. Filtering the candidates by this
# dataset's own country name, mapped to the ISO code Ignav returns,
# fixes it — covers every country name this app's datasets use.
COUNTRY_TO_ISO2 = {
    "Algeria": "DZ", "Argentina": "AR", "Australia": "AU", "Austria": "AT",
    "Bahrain": "BH", "Bangladesh": "BD", "Belgium": "BE", "Brazil": "BR",
    "Bulgaria": "BG", "Canada": "CA", "China": "CN", "Colombia": "CO",
    "Croatia": "HR", "Cyprus": "CY", "Czech Republic": "CZ", "Denmark": "DK",
    "Dominican Republic": "DO", "Ecuador": "EC", "Egypt": "EG",
    "El Salvador": "SV", "Finland": "FI", "France": "FR", "Germany": "DE",
    "Ghana": "GH", "Greece": "GR", "Hong Kong": "HK", "Hungary": "HU",
    "Iceland": "IS", "India": "IN", "Indonesia": "ID", "Iran": "IR",
    "Ireland": "IE", "Israel": "IL", "Italy": "IT", "Japan": "JP",
    "Kuwait": "KW", "Lebanon": "LB", "Luxembourg": "LU", "Malaysia": "MY",
    "Mexico": "MX", "Morocco": "MA", "Netherlands": "NL",
    "New Zealand": "NZ", "Nigeria": "NG", "Norway": "NO", "Panama": "PA",
    "Peru": "PE", "Poland": "PL", "Portugal": "PT", "Romania": "RO",
    "Russia": "RU", "Saudi Arabia": "SA", "Serbia": "RS", "Singapore": "SG",
    "Slovenia": "SI", "South Africa": "ZA", "South Korea": "KR",
    "Spain": "ES", "Sweden": "SE", "Switzerland": "CH", "Taiwan": "TW",
    "Thailand": "TH", "Tunisia": "TN", "Turkey": "TR", "UAE": "AE",
    "Ukraine": "UA", "United Kingdom": "GB", "United States": "US",
    "Uruguay": "UY", "Uzbekistan": "UZ", "Vietnam": "VN",
}

# Ignav's own search provider only supports a limited forward window
# (observed to fail somewhere between ~330 and ~365 days out) — surfaced
# here so the frontend can set sensible date-picker bounds instead of
# students hitting a confusing provider error.
MAX_DAYS_AHEAD = 330


class FlightSearchError(Exception):
    """A clean, user-facing reason a flight search didn't return a
    price — Ignav's own error messages are already written for a
    reader, so they're passed through rather than replaced."""


def _request(method: str, path: str, params=None, body=None):
    api_key = os.getenv("IGNAV_API_KEY")

    if not api_key:
        raise FlightSearchError(
            "Flight search isn't configured (no IGNAV_API_KEY set)."
        )

    url = f"{IGNAV_BASE_URL}{path}"

    if params:
        url += "?" + urllib.parse.urlencode(params)

    data = json.dumps(body).encode("utf-8") if body is not None else None

    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "X-Api-Key": api_key,
            **({"Content-Type": "application/json"} if data else {}),
        },
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read().decode("utf-8"))
            message = detail.get("error", {}).get("message") or str(error)
        except (ValueError, json.JSONDecodeError):
            message = str(error)

        raise FlightSearchError(message)

    except (urllib.error.URLError, TimeoutError):
        raise FlightSearchError("Could not reach the flight search service.")


def search_airports(query: str, limit: int = 5):
    """Real IATA airports matching a plain city or airport name —
    Ignav's airport search does not resolve full institution names, so
    callers must pass a bare city ("Boston"), not "MIT" or "Cambridge,
    MA, United States"."""

    if not query or len(query.strip()) < 2:
        return []

    return _request("GET", "/airports", params={"q": query.strip(), "limit": limit})


def resolve_destination_airport_candidates(
    city: str, country_name: str | None = None, lat=None, lon=None, limit: int = 3
):
    """
    Real airports for a university, nearest/most-relevant first, so a
    caller can try more than one — the single nearest airport to a
    smaller university town sometimes carries no real international
    fares at all (Oxford's own small airport has none; students
    actually fly via London), so a lone best guess isn't always
    enough. A bare city-name text match is ambiguous in two ways a
    country filter alone cannot fix — across countries (Cambridge, MA
    vs Cambridge, UK) and *within* one (Cambridge, MA vs
    Cambridge-Dorchester, Maryland, both say "US") — so when real
    coordinates are available, geography is trusted over text first:

    1. Use Geoapify to find real nearby airports by actual coordinates,
       then verify each against Ignav itself, nearest first, keeping
       every one that is both real and in the right country.
    2. Fall back to Ignav's own city-name search, filtered by country,
       for sources with no coordinates or no geo-verified match.
    3. Fall back further to any same-city match regardless of country,
       rather than an empty list — the caller always shows which
       airport was actually used before any price is trusted.
    """

    iso2 = COUNTRY_TO_ISO2.get(country_name) if country_name else None
    found = []
    seen_codes = set()

    def add(airport):
        if airport["code"] not in seen_codes:
            seen_codes.add(airport["code"])
            found.append(airport)

    if lat is not None and lon is not None:
        from src.accommodation import nearby_airport_cities

        for nearby in nearby_airport_cities(lat, lon):
            if len(found) >= limit:
                break

            for airport in search_airports(nearby["city"], limit=10):
                if not iso2 or airport.get("country") == iso2:
                    add(airport)
                    break

    if len(found) < limit:
        candidates = search_airports(city, limit=10)
        matching = [a for a in candidates if not iso2 or a.get("country") == iso2]

        for airport in (matching or candidates):
            if len(found) >= limit:
                break
            add(airport)

    return found


def search_round_trip(
    origin_code: str, destination_code: str,
    departure_date: str, return_date: str, adults: int = 1
):
    """
    The cheapest real round-trip itineraries for a route and dates, or
    raises FlightSearchError with a message suitable to show the
    student directly.
    """

    data = _request("POST", "/fares/round-trip", body={
        "origin": origin_code,
        "destination": destination_code,
        "departure_date": departure_date,
        "return_date": return_date,
        "adults": adults,
    })

    itineraries = data.get("itineraries", [])

    if not itineraries:
        raise FlightSearchError(
            f"No {origin_code}→{destination_code} fares found for those dates."
        )

    itineraries.sort(key=lambda it: it["price"]["amount"])

    return [
        {
            "ignav_id": it["ignav_id"],
            "price_amount": it["price"]["amount"],
            "price_currency": it["price"]["currency"],
            "outbound_carrier": it["outbound"].get("carrier"),
            "outbound_duration_minutes": it["outbound"].get("duration_minutes"),
            "inbound_carrier": (it.get("inbound") or {}).get("carrier"),
            "inbound_duration_minutes": (it.get("inbound") or {}).get("duration_minutes"),
            "stops_outbound": max(0, len(it["outbound"].get("segments", [])) - 1),
        }
        for it in itineraries[:5]
    ]


def get_booking_links(ignav_id: str):
    """Real booking URLs (airline and/or third-party) for one searched
    itinerary, so a student can act on the price shown rather than
    just see a number with nowhere to go."""

    data = _request("POST", "/fares/booking-links", body={"ignav_id": ignav_id})

    links = []

    for option in data.get("booking_options", []):
        for link in option.get("links", []):
            links.append({
                "provider_name": link.get("provider_name"),
                "provider_type": link.get("provider_type"),
                "url": link.get("url"),
            })

    return links
