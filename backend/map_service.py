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
# These map to strict Google Place "types" to avoid irrelevant keyword matches.
# e.g. "bar" as a type excludes "Espresso Bar" (which is a cafe).
CATEGORY_MAPPINGS = {
    "art": "art_gallery|museum",
    "history": "museum|tourist_attraction",
    "nature": "park|garden",
    "shopping": "clothing_store|shopping_mall",
    "cafes": "cafe",
    "desserts": "bakery",
    "nightlife": "bar|night_club",
}

# -------------------------
# Fetch places from Google API
# -------------------------
def fetch_places(lat: float, lng: float, radius: int, category: str) -> List[dict]:
    """
    Uses Google Nearby Search API with default prominence sorting
    """
    # Check if we have a strict type mapping
    mapped_types = CATEGORY_MAPPINGS.get(category.lower())

    url = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    all_results = []

    # If we have mapped types (e.g. "bar|night_club"), split them and fetch each strictly
    if mapped_types:
        types_list = mapped_types.split("|")
        for t in types_list:
            params = {
                "location": f"{lat},{lng}",
                "radius": radius,
                "type": t,  # Strict type filtering
                "key": GOOGLE_KEY
            }
            res = requests.get(url, params=params, timeout=10)
            data = res.json()
            all_results.extend(data.get("results", []))
            
    else:
        # Fallback to keyword search for unmapped categories
        params = {
            "location": f"{lat},{lng}",
            "radius": radius,
            "keyword": category,
            "key": GOOGLE_KEY
        }
        res = requests.get(url, params=params, timeout=10)
        data = res.json()
        all_results.extend(data.get("results", []))

    return all_results


def generate_places(request: QuestRequest) -> List[dict]:
    radius = max(int(request.radius * 1000), 500)
    
    # Interpret 'popularity' as the Diversity Slider (1 = Best Only, 5 = Most Diverse)
    # If value is >= 3, we enforce category diversity. If < 3, we just pick the top rated places.
    prioritize_diversity = request.popularity >= 3
    
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

    # 2. Selection Strategy
    # Dynamic pool size: fetch enough candidates for the optimizer
    # e.g., if we need 5 stops, fetch ~15 options to choose from.
    estimated_stops = get_stop_count(request.route_min, None)
    pool_size = max(estimated_stops * 3, 20)

    num_cats = len(request.categories)
    if num_cats == 0:
        return []
    
    selected_places = []
    seen_ids = set()

    if prioritize_diversity:
        # STRATEGY A: Balanced Selection (Round-Robin / Quota)
        target_per_cat = math.ceil(pool_size / num_cats)
        
        # Pass 1: Fill quotas
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
        
        # Pass 2: Fill remainder
        if len(selected_places) < pool_size:
            remaining = []
            for cat in request.categories:
                for p in places_by_category.get(cat, []):
                    pid = p.get("place_id")
                    if pid and pid not in seen_ids:
                        remaining.append(p)
            remaining.sort(key=lambda x: x["_score"], reverse=True)
            selected_places.extend(remaining[:(pool_size - len(selected_places))])
            
    else:
        # STRATEGY B: Best Only (Global Sort)
        all_candidates = []
        for cat in request.categories:
            all_candidates.extend(places_by_category.get(cat, []))
        
        all_candidates.sort(key=lambda x: x["_score"], reverse=True)
        
        for p in all_candidates:
            if len(selected_places) >= pool_size:
                break
            pid = p.get("place_id")
            if pid and pid not in seen_ids:
                seen_ids.add(pid)
                selected_places.append(p)

    logger.info(f"Selected {len(selected_places)} places. Mode: {'Diversity' if prioritize_diversity else 'Best Only'}")

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