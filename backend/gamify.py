import os
import logging
import requests
from typing import List, Dict, Tuple
from dotenv import load_dotenv, find_dotenv
import sys

load_dotenv(find_dotenv())
MAPBOX_KEY = os.getenv("MAPBOX_KEY")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not MAPBOX_KEY:
    logger.error("MAPBOX_KEY is not set. Please check that your .env file exists and contains MAPBOX_KEY.")


def get_mapbox_route(
    user_location: Tuple[float, float],
    places: List[Dict],
    mode: str = "walking"  # 'walking' or 'driving'
) -> List[Dict]:
    """
    Returns the places in optimal visiting order using Mapbox Optimization API.
    
    user_location: (lat, lng)
    places: list of dicts with 'lat' and 'lng'
    mode: 'walking' or 'driving', taken from user input
    """
    # Validate mode
    if mode not in ["walking", "driving"]:
        raise ValueError("Transport mode must be 'walking' or 'driving'")
    
    if not places:
        return None, 0

    # Build coordinates string: lng,lat;lng,lat;...
    coords = []
    coords.append(f"{user_location[1]},{user_location[0]}")
    coords += [f"{p['lng']},{p['lat']}" for p in places]
    coord_str = ";".join(coords)

    url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord_str}"
    params = {
        "access_token": MAPBOX_KEY,
        "source": "first",
        "roundtrip": "true",
        "geometries": "geojson" # useful for map visualization
    }

    res = requests.get(url, params=params, timeout=15)
    data = res.json()

    # Fallback if API fails
    if "trips" not in data or not data["trips"]:
        logger.error(f"Mapbox API failed or returned no trips. Data: {data}")
        return None, 0

    trip = data["trips"][0]

    # Extract waypoint order from the root 'waypoints' key
    # The 'waypoints' array in response corresponds to input order.
    # Each waypoint has a 'waypoint_index' indicating its position in the trip.
    waypoints = data.get("waypoints", [])
    
    # Sort input indices by their position in the trip
    # enumerate gives (input_index, waypoint_data)
    sorted_inputs = sorted(enumerate(waypoints), key=lambda x: x[1]["waypoint_index"])
    
    # Extract places in order. Index 0 is user location (skip it).
    ordered_places = []
    for input_idx, _wp in sorted_inputs:
        if input_idx == 0:
            continue
        ordered_places.append(places[input_idx - 1])

    # Return ordering and duration (seconds)
    return ordered_places, int(trip.get("duration", 0))


def optimize_for_duration(
    user_location: Tuple[float, float],
    candidates: List[Dict],
    target_minutes: int,
    mode: str = "walking",
    attempts_per_size: int = 5,
    tolerance: float = 0.15,
):
    """
    Try to find a subset and ordering of `candidates` such that the total travel
    time (in minutes) is within `tolerance` fraction of `target_minutes`.

    Strategy: for subset sizes from 1..len(candidates), try a few random subsets
    and call Mapbox optimized-trips for each to get duration. Return the first
    ordering that matches the target within tolerance, or the best-effort closest.
    """
    import random

    target_seconds = target_minutes * 60
    best = None
    best_diff = None

    n = len(candidates)
    if n == 0:
        return [], 0

    # Try decreasing subset sizes to maximize places visited
    # Start from max possible (11 or n) down to 1
    for size in range(min(11, n), 0, -1):
        for _ in range(attempts_per_size):
            subset = random.sample(candidates, size)

            try:
                ordered, duration = get_mapbox_route(user_location, subset, mode=mode)
            except Exception as e:
                logger.error(f"Error optimizing subset of size {size}: {e}")
                # If mapbox call fails, skip this subset
                continue

            if ordered is None:
                continue

            diff = abs(duration - target_seconds)
            if best is None or diff < best_diff:
                best = (ordered, duration)
                best_diff = diff

            # If we are under the time limit, this is the best we can do in terms of count
            # (since we are iterating from largest count downwards)
            if duration <= target_seconds:
                return ordered, duration

    # Return best effort
    if best:
        return best[0], best[1]

    # Fallback: return original candidates unchanged with zero duration
    return candidates, 0
