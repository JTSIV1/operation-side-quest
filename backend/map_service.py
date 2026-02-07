import os
import logging
import requests
from typing import List, Optional
from dotenv import load_dotenv, find_dotenv
import math

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
# Category Mappings
# -------------------------
CATEGORY_MAPPINGS = {
    "art": "art_gallery|museum",
    "history": "museum|historical_landmark",
    "nature": "park|garden",
    "shopping": "clothing_store",
    "cafes": "cafe",
    "desserts": "bakery|ice_cream_shop",
    "nightlife": "bar|night_club",
}

# -------------------------
# Fetch places from Google API
# -------------------------
def fetch_places(lat: float, lng: float, radius: int, category: str) -> List[dict]:
    """
    Uses Google Nearby Search API with default prominence sorting
    """
    # Map generic terms to specific Google keywords to avoid "art supply stores"
    search_keyword = CATEGORY_MAPPINGS.get(category.lower(), category)

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    params = {
        "location": f"{lat},{lng}",
        "radius": radius,     # required for prominence
        "keyword": search_keyword,
        "key": GOOGLE_KEY
    }

    res = requests.get(url, params=params, timeout=10)
    data = res.json()
    
    if data.get("error_message"):
        logger.error(f"Google API error message: {data.get('error_message')}")

    return data.get("results", [])


def generate_places(request: QuestRequest) -> List[dict]:
    radius = max(int(request.radius * 1000), 500)
    top_k = request.popularity
    
    # Helper for scoring
    def get_popularity_score(place):
        rating = place.get("rating", 0)
        reviews = place.get("user_ratings_total", 0)
        return rating * math.log10(reviews + 1)

    # 1. Fetch, Filter, and Score by Category
    places_by_category = {}
    for cat in request.categories:
        raw_results = fetch_places(request.latitude, request.longitude, radius, cat)
        
        filtered_cat = []
        for p in raw_results:
            # Filter: Budget & Min Reviews
            if p.get("price_level", 0) <= request.budget and p.get("user_ratings_total", 0) >= 5:
                # Calculate score immediately for sorting
                p["_score"] = get_popularity_score(p)
                filtered_cat.append(p)
        
        # Sort this category by score descending
        filtered_cat.sort(key=lambda x: x["_score"], reverse=True)
        places_by_category[cat] = filtered_cat

    # 2. Balanced Selection (Round-Robin / Quota)
    pool_size = max(top_k * 4, 20)
    num_cats = len(request.categories)
    if num_cats == 0:
        return []

    target_per_cat = math.ceil(pool_size / num_cats)
    
    selected_places = []
    seen_ids = set()

    # Pass 1: Fill quotas for each category
    for cat in request.categories:
        candidates = places_by_category.get(cat, [])
        count = 0
        for p in candidates:
            if count >= target_per_cat:
                break
            pid = p.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                selected_places.append(p)
                count += 1
    
    # Pass 2: If we haven't met pool_size, fill with the highest scoring remaining places
    if len(selected_places) < pool_size:
        remaining = []
        for cat in request.categories:
            for p in places_by_category.get(cat, []):
                pid = p.get("place_id")
                if pid and pid not in seen_ids:
                    remaining.append(p)
        
        # Sort remaining globally by score
        remaining.sort(key=lambda x: x["_score"], reverse=True)
        needed = pool_size - len(selected_places)
        selected_places.extend(remaining[:needed])

    logger.info(f"Selected {len(selected_places)} places with balanced categories.")

    return [
        {
            "name": p["name"],
            "lat": p["geometry"]["location"]["lat"],
            "lng": p["geometry"]["location"]["lng"],
            "rating": p.get("rating", 0),
            "user_ratings_total": p.get("user_ratings_total", 0),
            "address": p.get("vicinity", "")
        }
        for p in selected_places
    ]