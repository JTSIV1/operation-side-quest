from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import json

from inputparams import QuestRequest
import map_service
import gamify
import db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

logger = logging.getLogger("uvicorn")


@app.on_event("startup")
def startup_event():
    db.init_db()

class GenerateQuestResponse(BaseModel):
    requested: dict
    selected_places: List[dict]
    ordered_places: List[dict]
    travel_time_minutes: int


class SignupRequest(BaseModel):
    email: str
    username: str
    password: str
    first_name: str
    last_name: str


class LoginRequest(BaseModel):
    email: str
    password: str

class AddFriendRequest(BaseModel):
    user_id: str
    friend_email: str

class RemoveFriendRequest(BaseModel):
    user_id: str
    friend_id: str

class SaveRouteRequest(BaseModel):
    user_id: str
    route_data: dict


@app.post("/signup")
def signup(req: SignupRequest):
    user_id = db.create_user(
        req.email, req.username, req.password, req.first_name, req.last_name
    )
    if not user_id:
        raise HTTPException(
            status_code=400, 
            detail="User with this email or username already exists."
        )
    return {"user_id": user_id}


@app.post("/login")
def login(req: LoginRequest):
    user_id = db.verify_user(req.email, req.password)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    return {"user_id": user_id}


@app.post("/generate-quest", response_model=GenerateQuestResponse)
def generate_quest(req: QuestRequest):
    """
    1) Use `map_service.generate_places` to fetch top-K places based on the user's QuestRequest.
    2) Call `gamify.get_mapbox_route` to compute an optimized visiting order starting from the user's location.
    """
    logger.info(
        "Received generate-quest request: categories=%s budget=%s route_min=%s driving=%s radius=%.2f",
        req.categories,
        req.budget,
        req.route_min,
        req.driving,
        req.radius,
    )
    # 1) Generate candidate places using existing logic (top_n candidates)
    try:
        places = map_service.generate_places(req)
    except Exception as e:
        logger.exception("Failed to generate places")
        raise HTTPException(status_code=500, detail=f"Error generating places: {e}")

    if not places:
        return GenerateQuestResponse(
            requested=req.dict(),
            selected_places=[],
            ordered_places=[],
            travel_time_minutes=0
        )

    # 2) Map transport input to Mapbox mode
    mode = "driving" if req.driving else "walking"

    # 3) Compute optimized order that matches requested travel time
    try:
        ordered, duration_seconds = gamify.optimize_for_duration(
            (req.latitude, req.longitude), places, req.route_min, mode=mode
        )
    except Exception:
        logger.exception("Mapbox route optimization failed, returning un-ordered places")
        ordered = places
        duration_seconds = 0

    travel_time_minutes = int(round(duration_seconds / 60))

    return GenerateQuestResponse(
        requested=req.dict(),
        selected_places=places,
        ordered_places=ordered,
        travel_time_minutes=travel_time_minutes
    )

@app.post("/save-route")
def save_route(req: SaveRouteRequest):
    data = req.route_data
    # Determine number of stops from the route data
    places = data.get("ordered_places") or data.get("selected_places") or []
    num_stops = len(places)
    
    route_id = db.create_route(req.user_id, json.dumps(data), num_stops)
    if not route_id:
        raise HTTPException(status_code=500, detail="Failed to save route")
    
    return {"route_id": route_id, "message": "Route saved successfully"}

@app.get("/saved-routes/{user_id}")
def get_saved_routes(user_id: str):
    routes = db.get_user_routes(user_id)
    # Parse the route_data JSON string so the frontend gets a proper object
    for r in routes:
        if r["route_data"]:
            try:
                r["route_data"] = json.loads(r["route_data"])
            except:
                r["route_data"] = {}
    return routes

@app.post("/add-friend")
def add_friend(req: AddFriendRequest):
    result = db.add_friend(req.user_id, req.friend_email)
    if result == "Success":
        return {"message": "Friend request sent"}
    elif result == "User not found":
        raise HTTPException(status_code=404, detail="User with this email not found.")
    elif result == "Cannot add yourself":
        raise HTTPException(status_code=400, detail="You cannot add yourself as a friend.")
    elif result == "Request already sent":
        raise HTTPException(status_code=400, detail="Friend request already sent or you are already friends.")
    else:
        raise HTTPException(status_code=500, detail=f"Database error: {result}")

@app.post("/remove-friend")
def remove_friend(req: RemoveFriendRequest):
    result = db.remove_friend(req.user_id, req.friend_id)
    if result == "Success":
        return {"message": "Removed successfully"}
    else:
        raise HTTPException(status_code=500, detail=f"Database error: {result}")

@app.get("/friends/{user_id}")
def get_friends(user_id: str):
    return db.get_friends(user_id)

@app.get("/friends/requests/incoming/{user_id}")
def get_incoming_requests(user_id: str):
    return db.get_incoming_requests(user_id)

@app.get("/friends/requests/pending/{user_id}")
def get_pending_requests(user_id: str):
    return db.get_pending_requests(user_id)
