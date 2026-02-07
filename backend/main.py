from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import json
from datetime import datetime

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
    name: str

class DeleteRouteRequest(BaseModel):
    user_id: str
    route_id: str

class UpdateRouteStatusRequest(BaseModel):
    route_id: str
    completed: bool

class ShareRouteRequest(BaseModel):
    route_id: str
    friend_email: str

class RemoveRouteParticipantRequest(BaseModel):
    route_id: str
    user_id: str

class UpdateUserRequest(BaseModel):
    user_id: str
    username: str
    first_name: str
    last_name: str


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
    
    route_id = db.create_route(req.user_id, json.dumps(data), num_stops, req.name)
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

@app.post("/delete-route")
def delete_route_endpoint(req: DeleteRouteRequest):
    res = db.delete_route(req.route_id, req.user_id)
    if res == "Success":
        return {"message": "Route deleted"}
    else:
        raise HTTPException(status_code=500, detail=res)

@app.post("/update-route-status")
def update_route_status(req: UpdateRouteStatusRequest):
    db.toggle_route_completion(req.route_id, req.completed)
    return {"message": "Status updated"}

@app.post("/share-route")
def share_route(req: ShareRouteRequest):
    res = db.add_route_participant(req.route_id, req.friend_email)
    if res == "Success":
        return {"message": "Friend added to route"}
    elif res == "User not found":
        raise HTTPException(status_code=404, detail="User not found")
    else:
        raise HTTPException(status_code=400, detail=res)

@app.get("/route-participants/{route_id}")
def get_route_participants(route_id: str):
    return db.get_route_participants(route_id)

@app.post("/remove-route-participant")
def remove_route_participant(req: RemoveRouteParticipantRequest):
    res = db.remove_route_participant(req.route_id, req.user_id)
    if res == "Success":
        return {"message": "Participant removed"}
    else:
        raise HTTPException(status_code=500, detail=res)

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

@app.get("/user/{user_id}")
def get_user_endpoint(user_id: str):
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/update-user")
def update_user_endpoint(req: UpdateUserRequest):
    res = db.update_user(req.user_id, req.username, req.first_name, req.last_name)
    if res == "Success":
        return {"message": "Profile updated"}
    elif res == "Username already taken":
        raise HTTPException(status_code=400, detail=res)
    else:
        raise HTTPException(status_code=500, detail=res)
@app.get("/leaderboard/{user_id}")
def get_leaderboard(user_id: str):
    # Get current user
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get friends
    friends = db.get_friends(user_id)
    
    # Combine user and friends
    participants = [user] + friends
    
    leaderboard_data = []
    locations = []
    now = datetime.now()
    
    for p in participants:
        routes = db.get_user_routes(p["id"])
        all_time_points = 0
        month_points = 0
        
        for r in routes:
            if r["completed"]:
                # Points calculation: 150 points per stop
                points = (r["num_stops"] or 0) * 150
                all_time_points += points
                
                # Extract locations for map
                r_data = r["route_data"]
                if r_data and isinstance(r_data, str):
                    try:
                        r_data = json.loads(r_data)
                    except:
                        r_data = {}
                
                if isinstance(r_data, dict):
                    places = r_data.get("ordered_places") or r_data.get("selected_places") or []
                    for place in places:
                        locations.append({
                            "lat": place["lat"],
                            "lng": place["lng"],
                            "place_name": place["name"],
                            "visitor_name": f"{p['first_name']} {p['last_name']}",
                            "visitor_id": p["id"]
                        })

                if r["time_completed"]:
                    try:
                        dt = datetime.fromisoformat(r["time_completed"])
                        if dt.year == now.year and dt.month == now.month:
                            month_points += points
                    except ValueError:
                        pass
        
        leaderboard_data.append({
            "id": p["id"],
            "username": p["username"],
            "first_name": p["first_name"],
            "last_name": p["last_name"],
            "all_time": all_time_points,
            "month": month_points
        })
    
    return {
        "all_time": sorted(leaderboard_data, key=lambda x: x["all_time"], reverse=True),
        "month": sorted(leaderboard_data, key=lambda x: x["month"], reverse=True),
        "locations": locations
    }
