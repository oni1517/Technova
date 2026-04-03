import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.db import Database
from backend.models import Coordinate, PatientInput, RouteMap, TriageResponse
from backend.routing import select_best_hospital
from backend.triage import classify_patient
from backend.utils import send_sms_alert

logging.basicConfig(level=logging.INFO)

settings = get_settings()
database = Database(settings.database_url)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    yield
    await database.close()


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend")


@app.get("/")
async def home() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "database_mode": "fallback" if database.fallback_mode else "postgres",
        "anthropic_model": settings.anthropic_model,
    }


@app.post("/api/triage", response_model=TriageResponse)
async def triage_patient(payload: PatientInput) -> TriageResponse:
    try:
        triage = await classify_patient(payload, settings)
        routing_preface: list[str] = []

        filtered_hospitals = await database.fetch_hospitals(
            department=None if triage.severity == "critical" else triage.department,
            icu_only=triage.severity == "critical",
        )
        if not filtered_hospitals:
            if triage.severity != "critical":
                routing_preface.append(
                    f"No hospitals currently advertise {triage.department}; expanded search to all hospitals."
                )
            filtered_hospitals = await database.fetch_hospitals()

        selected_hospital, candidate_hospitals, override_applied, routing_reasoning = await select_best_hospital(
            patient=payload,
            triage=triage,
            hospitals=filtered_hospitals,
            settings=settings,
        )

        sms_result = await send_sms_alert(
            patient=payload,
            triage=triage,
            hospital=selected_hospital,
            settings=settings,
        )

        map_data = RouteMap(
            patient=Coordinate(lat=payload.patient_lat, lon=payload.patient_lon),
            destination=(
                Coordinate(lat=selected_hospital.lat, lon=selected_hospital.lon)
                if selected_hospital
                else None
            ),
            polyline=(
                [
                    Coordinate(lat=payload.patient_lat, lon=payload.patient_lon),
                    Coordinate(lat=selected_hospital.lat, lon=selected_hospital.lon),
                ]
                if selected_hospital
                else []
            ),
        )

        return TriageResponse(
            triage=triage,
            override_applied=override_applied,
            selected_hospital=selected_hospital,
            candidate_hospitals=candidate_hospitals,
            routing_reasoning=routing_preface + routing_reasoning,
            sms=sms_result,
            map_data=map_data,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process triage request: {exc}") from exc
