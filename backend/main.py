import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import get_settings
from backend.db import Database
from backend.models import Coordinate, PatientInput, RouteMap, TriageResponse, VoiceCallInput
from backend.routing import select_best_hospital
from backend.triage import classify_patient
from backend.utils import mask_phone_number, queue_bolna_vobiz_call, send_sms_alert

logging.basicConfig(level=logging.INFO)

startup_settings = get_settings()
database = Database(startup_settings.database_url)

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"


@asynccontextmanager
async def lifespan(_: FastAPI):
    await database.connect()
    yield
    await database.close()


app = FastAPI(title=startup_settings.app_name, debug=startup_settings.debug, lifespan=lifespan)

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
    runtime_settings = get_settings()
    return {
        "status": "ok",
        "database_mode": "fallback" if database.fallback_mode else "postgres",
        "anthropic_model": runtime_settings.anthropic_model,
        "voice_provider": f"bolna_{runtime_settings.bolna_provider}",
        "voice_ready": "true" if all([runtime_settings.bolna_api_key, runtime_settings.bolna_agent_id]) else "false",
        "voice_default_recipient_configured": (
            "true" if bool(runtime_settings.bolna_default_recipient_phone_number) else "false"
        ),
        "voice_default_recipient_masked": mask_phone_number(runtime_settings.bolna_default_recipient_phone_number) or "",
    }


async def build_triage_response(
    payload: PatientInput,
    trigger_voice_call: bool = False,
    recipient_phone_number: str | None = None,
) -> TriageResponse:
    try:
        runtime_settings = get_settings()
        triage = await classify_patient(payload, runtime_settings)
        hospitals = await database.fetch_hospitals()

        selected_hospital, candidate_hospitals, override_applied, routing_reasoning = await select_best_hospital(
            patient=payload,
            triage=triage,
            hospitals=hospitals,
        )

        sms_result = await send_sms_alert(
            patient=payload,
            triage=triage,
            hospital=selected_hospital,
            settings=runtime_settings,
        )
        voice_call_result = (
            await queue_bolna_vobiz_call(
                patient=payload,
                triage=triage,
                hospital=selected_hospital,
                settings=runtime_settings,
                recipient_phone_number=recipient_phone_number,
            )
            if trigger_voice_call
            else None
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
            routing_reasoning=routing_reasoning,
            sms=sms_result,
            voice_call=voice_call_result,
            map_data=map_data,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process triage request: {exc}") from exc


@app.post("/api/triage", response_model=TriageResponse)
async def triage_patient(payload: PatientInput) -> TriageResponse:
    return await build_triage_response(payload)


@app.post("/api/voice/test-call", response_model=TriageResponse)
async def triage_and_queue_voice_call(payload: VoiceCallInput) -> TriageResponse:
    return await build_triage_response(
        payload=payload,
        trigger_voice_call=True,
        recipient_phone_number=payload.recipient_phone_number,
    )
