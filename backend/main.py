from dotenv import load_dotenv
load_dotenv()

import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List

from inputparams import QuestRequest
import map_service
import gamify

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

logger = logging.getLogger("uvicorn")


class GenerateQuestResponse(BaseModel):
    requested: dict
    selected_places: List[dict]
    ordered_places: List[dict]
    travel_time_minutes: int


@app.post("/generate-quest", response_model=GenerateQuestResponse)
def generate_quest(req: QuestRequest):
    """
    1) Use `map_service.generate_places` to fetch top-K places based on the user's QuestRequest.
    2) Call `gamify.get_mapbox_route` to compute an optimized visiting order starting from the user's location.
    """
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
