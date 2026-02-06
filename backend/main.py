import os
from fastapi import FastAPI
from dotenv import load_dotenv
import googlemaps

load_dotenv()
GMAPS_API_KEY = os.getenv("GMAPS_API_KEY")
if not GMAPS_API_KEY:
    raise RuntimeError("GMAPS_API_KEY is required but not set")
gmaps = googlemaps.Client(key=GMAPS_API_KEY)

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}
