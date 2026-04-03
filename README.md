# Golden Hour Emergency Triage & Routing System

Demo-ready hackathon boilerplate for ambulance triage, hospital matching, ICU override routing, and SMS alerting.

## Stack

- FastAPI backend with async endpoints
- Anthropic Claude triage using tool-schema structured output
- PostgreSQL / Neon via asyncpg
- Twilio SMS alerting
- Plain HTML, CSS, and JavaScript frontend
- Leaflet route map

## Project Structure

```text
backend/
  __init__.py
  config.py
  db.py
  main.py
  models.py
  routing.py
  triage.py
  utils.py
frontend/
  index.html
  script.js
  style.css
requirements.txt
.env.example
README.md
```

## Quick Start

1. Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Copy env values:

```bash
cp .env.example .env
```

3. Start the app:

```bash
uvicorn backend.main:app --reload
```

4. Open:

```text
http://127.0.0.1:8000
```

## Notes

- If `DATABASE_URL` is set, the app creates and seeds the PostgreSQL `hospitals` table automatically.
- If `DATABASE_URL` is missing or unavailable, the app falls back to in-memory Pune hospital seed data so the demo still works.
- If Anthropic credentials are missing or the API call fails, the app falls back to rules-based triage.
- If Twilio credentials are missing, the app still returns the prepared SMS body and marks SMS delivery as skipped.

