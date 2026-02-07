from pydantic import BaseModel
from typing import List, Optional


class QuestRequest(BaseModel):
    lat: float
    lng: float
    categories: List[str]
    # time_minutes now represents the total travel time the user wants to spend
    # walking/driving (minutes). Time spent at stops is not included.
    time_minutes: int
    transport: str
    budget: int
    # Instead of max_stops, user supplies top_n candidate places to consider
    top_n: Optional[int] = 10
