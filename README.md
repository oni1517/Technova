# Golden Hour Emergency Triage & Routing System

Demo-ready hackathon boilerplate for ambulance triage, hospital matching, ICU override routing, and SMS alerting.

## Stack

- FastAPI backend with async endpoints
- Anthropic Claude triage using tool-schema structured output
- PostgreSQL / Neon via asyncpg
- Twilio SMS alerting
- Bolna Voice AI outbound call trigger for agents configured with Vobiz
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

## Bolna + Vobiz Test Call

The app now includes a `Run Triage + Voice Call` action in the UI and a backend endpoint at `/api/voice/test-call`.

This implementation uses the Bolna outbound call API and assumes your Bolna agent is already configured to use `Vobiz` as its telephony provider inside the Bolna dashboard.

Set these env vars in `.env`:

```env
BOLNA_API_KEY=your_bolna_api_key
BOLNA_AGENT_ID=your_bolna_agent_id
BOLNA_FROM_PHONE_NUMBER=your_vobiz_or_bolna_enabled_number
BOLNA_DEFAULT_RECIPIENT_PHONE_NUMBER=destination_number_for_test_calls
BOLNA_PROVIDER=vobiz
```

Then:

1. Start the app with `uvicorn backend.main:app --reload`.
2. Open `http://127.0.0.1:8000`.
3. Fill the patient form.
4. Optionally enter a `Voice Test Number` in E.164 format such as `+911234567890`.
5. Click `Run Triage + Voice Call`.

If the Bolna call is accepted, the response includes a queued status and execution id in the reasoning panel.

You can also test it directly with `curl`:

```bash
curl -X POST http://127.0.0.1:8000/api/voice/test-call \
  -H "Content-Type: application/json" \
  -d '{
    "heart_rate": 132,
    "systolic_bp": 92,
    "diastolic_bp": 58,
    "oxygen_saturation": 89,
    "injury": "Road traffic accident with chest trauma and heavy bleeding",
    "patient_lat": 18.5204,
    "patient_lon": 73.8567,
    "recipient_phone_number": "+911234567890"
  }'
```

## Notes

- If `DATABASE_URL` is set, the app creates and seeds the PostgreSQL `hospitals` table automatically.
- If `DATABASE_URL` is missing or unavailable, the app falls back to in-memory Pune hospital seed data so the demo still works.
- If Anthropic credentials are missing or the API call fails, the app falls back to rules-based triage.
- If Twilio credentials are missing, the app still returns the prepared SMS body and marks SMS delivery as skipped.
- If Bolna credentials are missing, the voice call flow still works end-to-end but returns `skipped` instead of queuing a call.
