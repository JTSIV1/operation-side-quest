import os
import logging
import requests
from typing import List, Optional
from dotenv import load_dotenv, find_dotenv

from inputparams import QuestRequest

load_dotenv(find_dotenv())

GOOGLE_KEY = os.getenv("GOOGLE_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not GOOGLE_KEY:
    logger.error("GOOGLE_KEY is not set. Please check that your .env file exists and contains GOOGLE_KEY.")

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

    res = requests.get(url, params=params, timeout=10)
    data = res.json()
    
    if data.get("error_message"):
        logger.error(f"Google API error message: {data.get('error_message')}")

    return data.get("results", [])


# -------------------------
# Main logic to generate places
# -------------------------
def generate_places(request: QuestRequest) -> List[dict]:
    # Frontend sends radius in km, convert to meters. Ensure min 500m.
    radius = max(int(request.radius * 1000), 500)
    top_k = request.popularity

    all_places = []

    # Fetch places for each category
    for cat in request.categories:
        results = fetch_places(request.latitude, request.longitude, radius, cat)
        all_places.extend(results)

    # Remove duplicates based on place_id
    seen = set()
    unique = []
    for p in all_places:
        pid = p.get("place_id")
        if pid and pid not in seen:
            seen.add(pid)
            unique.append(p)
            
    logger.info(f"Found {len(unique)} unique places before filtering.")

    # Filter by budget (Google price_level 0-4)
    filtered = [
        p for p in unique
        if p.get("price_level", 0) <= request.budget
    ]
    
    logger.info(f"Places remaining after budget filter: {len(filtered)}")

    # Pick top K based on Google’s default prominence order (filtered by rating)
    # Sort by rating then keep a larger pool for the optimizer to choose from
    # We use a multiplier (e.g. 4x) to give the route optimizer more flexibility
    pool_size = max(top_k * 4, 20)
    selected = sorted(filtered, key=lambda x: x.get("rating", 0), reverse=True)[:pool_size]
    
    logger.info(f"Selected {len(selected)} places to return (pool size: {pool_size}).")

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