import os
import requests
from typing import List, Dict, Tuple
from dotenv import load_dotenv

load_dotenv()
MAPBOX_KEY = os.getenv("MAPBOX_KEY")


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

    # Build coordinates string: lng,lat;lng,lat;...
    coords = [f"{user_location[1]},{user_location[0]}"]  # start point
    coords += [f"{p['lng']},{p['lat']}" for p in places]
    coord_str = ";".join(coords)

    url = f"https://api.mapbox.com/optimized-trips/v1/mapbox/{mode}/{coord_str}"
    params = {
        "access_token": MAPBOX_KEY,
        "source": "first",      # start at user_location
        "roundtrip": "false",   # don't return to start
        "geometries": "geojson" # useful for map visualization
    }

    res = requests.get(url, params=params, timeout=15)
    data = res.json()

    # Fallback if API fails
    if "trips" not in data or not data["trips"]:
        return places, 0

    trip = data["trips"][0]

    # Extract waypoint order (0 is user location)
    waypoints_order = [wp["waypoint_index"] for wp in trip["waypoints"]]

    # Map to places, skip first index (user location)
    ordered_places = [places[i-1] for i in waypoints_order if i != 0]

    # Return ordering and duration (seconds)
    return ordered_places, int(trip.get("duration", 0))


def optimize_for_duration(
    user_location: Tuple[float, float],
    candidates: List[Dict],
    target_minutes: int,
    mode: str = "walking",
    attempts_per_size: int = 8,
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

    # Try increasing subset sizes
    for size in range(1, n + 1):
        for _ in range(attempts_per_size):
            subset = random.sample(candidates, size)

            try:
                ordered, duration = get_mapbox_route(user_location, subset, mode=mode)
            except Exception:
                # If mapbox call fails, skip this subset
                continue

            diff = abs(duration - target_seconds)
            if best is None or diff < best_diff:
                best = (ordered, duration)
                best_diff = diff

            if diff <= tolerance * target_seconds:
                # Good enough
                return ordered, duration

    # Return best effort
    if best:
        return best[0], best[1]

    # Fallback: return original candidates unchanged with zero duration
    return candidates, 0
