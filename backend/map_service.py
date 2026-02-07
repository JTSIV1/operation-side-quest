import os
import requests
from typing import List, Optional
from dotenv import load_dotenv

from inputparams import QuestRequest

load_dotenv()

GOOGLE_KEY = os.getenv("GOOGLE_KEY")

# -------------------------
# Speeds in km/h for transport
# -------------------------
SPEEDS = {
    "walk": 5,
    "drive": 40
}


# -------------------------
# Calculate search radius from time + transport
# -------------------------
def get_radius_meters(time_minutes: int, transport: str) -> int:
    # normalize transport strings to the keys used in SPEEDS
    t = (transport or "").lower()
    if t in SPEEDS:
        speed = SPEEDS[t]
    elif t.startswith("walk"):
        speed = SPEEDS["walk"]
    elif t.startswith("drive"):
        speed = SPEEDS["drive"]
    else:
        # default to walking speed
        speed = SPEEDS["walk"]
    hours = time_minutes / 60
    distance_km = speed * hours

    # Only search half the distance (allow time to visit places too)
    radius_m = int(distance_km * 1000 * 0.5)

    # Minimum radius = 500m to ensure results
    return max(radius_m, 500)


# -------------------------
# Calculate number of stops
# -------------------------
def get_stop_count(time_minutes: int, max_stops: Optional[int]) -> int:
    if max_stops:
        return max_stops

    avg_visit_time = 20  # minutes per stop
    return max(1, time_minutes // avg_visit_time)


# -------------------------
# Fetch places from Google API
# -------------------------
def fetch_places(lat: float, lng: float, radius: int, category: str) -> List[dict]:
    """
    Uses Google Nearby Search API with default prominence sorting
    """
    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,     # required for prominence
        "keyword": category,
        "key": GOOGLE_KEY
    }

    res = requests.get(url, params=params)
    data = res.json()

    return data.get("results", [])


# -------------------------
# Main logic to generate places
# -------------------------
def generate_places(request: QuestRequest) -> List[dict]:
    radius = get_radius_meters(request.time_minutes, request.transport)
    top_k = request.top_n or 10

    all_places = []

    # Fetch places for each category
    for cat in request.categories:
        results = fetch_places(request.lat, request.lng, radius, cat)
        all_places.extend(results)

    # Remove duplicates based on place_id
    seen = set()
    unique = []
    for p in all_places:
        pid = p.get("place_id")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)

    # Filter by budget (Google price_level 0-4)
    filtered = [
        p for p in unique
        if p.get("price_level", 0) <= request.budget
    ]

    # Pick top K based on Google’s default prominence order (filtered by rating)
    # Sort by rating then keep top_k
    selected = sorted(filtered, key=lambda x: x.get("rating", 0), reverse=True)[:top_k]

    # Return only necessary info
    return [
        {
            "name": p["name"],
            "lat": p["geometry"]["location"]["lat"],
            "lng": p["geometry"]["location"]["lng"],
            "rating": p.get("rating", 0),
            "address": p.get("vicinity", "")
        }
        for p in selected
    ]