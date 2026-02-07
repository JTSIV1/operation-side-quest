# Operation Side-Quest

Operation Side-Quest is a gamified urban exploration platform designed to turn your free time into an adventure. Whether you have 30 minutes or a full afternoon, the application generates optimized "quests"—curated routes of interesting places like cafes, parks, museums, and shops—tailored to your location, budget, and interests.

## Features
- **Quest Generation**: Create custom routes based on available time, budget, and preferred categories (Art, History, Nature, Nightlife, etc.).
- **Route Optimization**: Uses Mapbox to calculate the most efficient path for walking or driving.
- **Gamification**: Earn points for every stop you visit and compete on the leaderboard with your friends.
- **Social**: Add friends, share routes, and see what quests others are embarking on.

## Setup

1. Create a `.env` file in the root directory in the format of `.env.example` and fill in your API keys.

2. Run the following commands in the root directory:

```bash
python -m venv venv

# on windows:
.\venv\Scripts\activate

# on mac:
source venv/bin/activate

pip install -r requirements.txt
```

## Run the application locally

In order to run our app, you need to run the backend and frontend simultaneously in two terminals. Starting in the root directory, open two terminals and run the following commands in each. The app will run live at [http://localhost:5000/](http://localhost:5000/)

### Run Frontend

```bash
python frontend/app.py
```

### Run Backend

```bash
cd backend
uvicorn main:app --reload
```