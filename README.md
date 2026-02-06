# Operation Side-Quest - Frontend

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

## Run Frontend

```bash
python frontend/app.py
```

## Run Backend

```bash
fastapi dev backend/main.py
```