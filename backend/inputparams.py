from pydantic import BaseModel
from typing import List, Optional


class QuestRequest(BaseModel):
    categories: List[str]
    longitude: float
    latitude: float
    radius: float
    driving: bool
    popularity: int
    budget: int
    datetime: str
    route_min: int
