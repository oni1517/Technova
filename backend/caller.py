"""Parallel Twilio Voice calling flows for hospital bed confirmation."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from twilio.twiml.voice_response import Gather, VoiceResponse

from backend.config import Settings
from backend.db import Database
from backend.models import HospitalOption, PatientInput
from backend.routing import select_best_hospital
from backend.triage import classify_patient

BASE_URL = "https://slick-buses-open.loca.lt"  # EDIT before running
TWILIO_PHONE_NUMBER = "+16415057583"  # EDIT: your Twilio number

PRACTICE_HOSPITAL_PHONES = {
    "hospital_1": "+919075003642",  # EDIT: replace with real number
    "hospital_2": "",  # EDIT: replace with real number
    "hospital_3": "",  # EDIT: replace with real number
    "hospital_4": "",  # EDIT: replace with real number
    "hospital_5": "",  # EDIT: replace with real number
}
PRACTICE_MODE = True  # Set False to use real DB phone numbers

MAX_PARALLEL_HOSPITAL_CALLS = 5
FINAL_CALL_STATUSES = {
    "accepted",
    "busy",
    "canceled",
    "cancelled",
    "completed",
    "declined",
    "failed",
    "invalid_input",
    "late_accept",
    "no-answer",
    "no_bed_available",
    "no_input",
    "skipped",
}

logger = logging.getLogger(__name__)
voice_router = APIRouter(prefix="/api/voice", tags=["voice"])


@dataclass
class VoiceCallHospitalState:
    """Track one hospital's outbound call state inside a live voice session."""

    hospital_id: int
    hospital_name: str
    phone_number: str | None
    eta_minutes: int
    distance_km: float
    score: float
    call_sid: str | None = None
    call_status: str = "pending"
    response_digit: str | None = None
    error: str | None = None
    twilio_error_code: str | None = None
    twilio_error_message: str | None = None
    answered_by: str | None = None


@dataclass
class VoiceCallSession:
    """Store the in-memory state for one parallel hospital calling batch."""

    session_id: str
    patient_payload: dict[str, Any]
    patient_summary: str
    severity: str
    department: str
    override_applied: bool
    routing_reasoning: list[str] = field(default_factory=list)
    selected_hospital_id: int | None = None
    reserved_hospital_id: int | None = None
    reservation_status: str = "pending"
    hospitals: dict[int, VoiceCallHospitalState] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


VOICE_CALL_SESSIONS: dict[str, VoiceCallSession] = {}
VOICE_CALL_SESSIONS_LOCK = asyncio.Lock()


def _normalized_base_url() -> str:
    """Return BASE_URL without a trailing slash to keep webhook routes stable."""
    return BASE_URL.strip().rstrip("/")


def _get_database(request: Request) -> Database:
    """Return the shared database instance registered on the FastAPI app state."""
    database = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status_code=500, detail="Database is not available on application state.")
    return database


def _get_settings(request: Request) -> Settings:
    """Return the shared settings instance registered on the FastAPI app state."""
    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        raise HTTPException(status_code=500, detail="Settings are not available on application state.")
    return settings


def _is_placeholder_value(value: str | None) -> bool:
    """Treat empty or template values as unconfigured so the feature can skip safely."""
    if value is None:
        return True

    normalized = value.strip()
    if not normalized:
        return True

    placeholder_fragments = ("YOUR-NGROK", "XXXXXXXX", "example.com")
    return any(fragment in normalized for fragment in placeholder_fragments)


def _resolve_caller_number(settings: Settings) -> str | None:
    """Use the hardcoded voice number when set, otherwise fall back to the existing Twilio env number."""
    if not _is_placeholder_value(TWILIO_PHONE_NUMBER):
        return TWILIO_PHONE_NUMBER
    return settings.twilio_from_number


def _voice_calling_enabled(settings: Settings) -> bool:
    """Check whether the shared Twilio credentials and caller metadata are configured."""
    return all(
        [
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            not _is_placeholder_value(BASE_URL),
            _resolve_caller_number(settings),
        ]
    )


def _practice_phone_number(index: int) -> str | None:
    """Return the practice-mode destination number for the given ranked hospital slot."""
    return PRACTICE_HOSPITAL_PHONES.get(f"hospital_{index}")


async def _resolve_hospital_phone_number(
    database: Database,
    hospital: HospitalOption,
    index: int,
) -> str | None:
    """Resolve the outbound phone number for a hospital in practice or real mode."""
    if PRACTICE_MODE:
        return _practice_phone_number(index)
    return await database.fetch_hospital_phone_number(hospital.id)


def _voice_prompt_for_hospital(session: VoiceCallSession, hospital: VoiceCallHospitalState) -> str:
    """Build the spoken prompt used in the Twilio gather flow."""
    return (
        f"Golden Hour emergency triage request for {hospital.hospital_name}. "
        f"Patient severity is {session.severity}. "
        f"Department requested is {session.department.replace('_', ' ')}. "
        f"Patient summary: {session.patient_summary}. "
        "Press 1 now if you can reserve a bed immediately. "
        "Press 2 now if no bed is available."
    )


def _render_twiml_response(response: VoiceResponse) -> Response:
    """Return a TwiML XML response with the correct content type."""
    return Response(content=str(response), media_type="application/xml")


def _session_snapshot(session: VoiceCallSession) -> dict[str, Any]:
    """Serialize an in-memory voice session into a JSON-safe structure."""
    hospitals = [
        {
            "hospital_id": hospital.hospital_id,
            "hospital_name": hospital.hospital_name,
            "phone_number": hospital.phone_number,
            "eta_minutes": hospital.eta_minutes,
            "distance_km": hospital.distance_km,
            "score": hospital.score,
            "call_sid": hospital.call_sid,
            "call_status": hospital.call_status,
            "response_digit": hospital.response_digit,
            "error": hospital.error,
            "twilio_error_code": hospital.twilio_error_code,
            "twilio_error_message": hospital.twilio_error_message,
            "answered_by": hospital.answered_by,
        }
        for hospital in session.hospitals.values()
    ]

    return {
        "session_id": session.session_id,
        "patient_payload": session.patient_payload,
        "patient_summary": session.patient_summary,
        "severity": session.severity,
        "department": session.department,
        "override_applied": session.override_applied,
        "routing_reasoning": session.routing_reasoning,
        "selected_hospital_id": session.selected_hospital_id,
        "reserved_hospital_id": session.reserved_hospital_id,
        "reservation_status": session.reservation_status,
        "practice_mode": PRACTICE_MODE,
        "hospitals": hospitals,
    }


async def _store_voice_session(session: VoiceCallSession) -> None:
    """Persist a live voice session in the module-level in-memory registry."""
    async with VOICE_CALL_SESSIONS_LOCK:
        VOICE_CALL_SESSIONS[session.session_id] = session


async def _get_voice_session(session_id: str) -> VoiceCallSession | None:
    """Load a live voice session from the module-level in-memory registry."""
    async with VOICE_CALL_SESSIONS_LOCK:
        return VOICE_CALL_SESSIONS.get(session_id)


async def _create_outbound_call(
    session_id: str,
    hospital: VoiceCallHospitalState,
    settings: Settings,
) -> None:
    """Start one outbound Twilio call and capture the SID or failure state."""
    caller_number = _resolve_caller_number(settings)
    if not hospital.phone_number or _is_placeholder_value(hospital.phone_number):
        hospital.call_status = "skipped"
        hospital.error = "Destination phone number is not configured for this hospital."
        return
    if not caller_number:
        hospital.call_status = "skipped"
        hospital.error = "Twilio caller number is not configured."
        return

    def _create_call() -> str:
        base_url = _normalized_base_url()
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        call = client.calls.create(
            to=hospital.phone_number,
            from_=caller_number,
            url=f"{base_url}/api/voice/twiml/{session_id}/{hospital.hospital_id}",
            method="POST",
            status_callback=f"{base_url}/api/voice/status/{session_id}/{hospital.hospital_id}",
            status_callback_method="POST",
            status_callback_event=["initiated", "ringing", "answered", "completed"],
        )
        return call.sid

    try:
        hospital.call_status = "initiated"
        hospital.call_sid = await asyncio.to_thread(_create_call)
    except TwilioRestException as exc:
        hospital.call_status = "failed"
        hospital.twilio_error_code = str(exc.code) if exc.code is not None else None
        hospital.twilio_error_message = exc.msg
        hospital.error = f"Twilio error {exc.code}: {exc.msg}" if exc.code is not None else str(exc)
        logger.exception(
            "Twilio failed outbound voice call for hospital_id=%s with code=%s. Error: %s",
            hospital.hospital_id,
            exc.code,
            exc,
        )
    except Exception as exc:
        hospital.call_status = "failed"
        hospital.error = str(exc)
        logger.exception(
            "Failed to place outbound voice call for hospital_id=%s. Error: %s",
            hospital.hospital_id,
            exc,
        )


async def _complete_outbound_call(
    call_sid: str,
    settings: Settings,
) -> None:
    """Request Twilio to end an active outbound call."""

    def _end_call() -> None:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        client.calls(call_sid).update(status="completed")

    try:
        await asyncio.to_thread(_end_call)
    except Exception as exc:
        logger.exception("Failed to complete outbound call sid=%s. Error: %s", call_sid, exc)


async def _cancel_other_active_calls(
    session: VoiceCallSession,
    accepted_hospital_id: int,
    settings: Settings,
) -> None:
    """Hang up the remaining active calls once one hospital confirms a bed."""
    cancellation_tasks: list[asyncio.Task[None]] = []

    for hospital in session.hospitals.values():
        if hospital.hospital_id == accepted_hospital_id:
            continue
        if not hospital.call_sid or hospital.call_status in FINAL_CALL_STATUSES:
            continue

        hospital.call_status = "canceled"
        cancellation_tasks.append(asyncio.create_task(_complete_outbound_call(hospital.call_sid, settings)))

    if cancellation_tasks:
        await asyncio.gather(*cancellation_tasks, return_exceptions=True)


async def _reserve_bed_for_session(
    database: Database,
    session: VoiceCallSession,
    hospital_id: int,
) -> str:
    """Reserve one bed for a session, preventing duplicate reservations across callbacks."""
    async with session.lock:
        if session.reserved_hospital_id is not None:
            return "already_reserved"

        reserved_hospital = await database.reserve_bed(hospital_id)
        if reserved_hospital is None:
            return "unavailable"

        session.reserved_hospital_id = hospital_id
        session.reservation_status = "reserved"
        return "reserved"


async def _read_twilio_form(request: Request) -> dict[str, str]:
    """Normalize the Twilio webhook form payload into plain strings."""
    form = await request.form()
    return {str(key): str(value).strip() for key, value in form.items()}


def _empty_twiml_message(message: str) -> Response:
    """Return a small spoken TwiML response for invalid or expired requests."""
    response = VoiceResponse()
    response.say(message, voice="alice")
    response.hangup()
    return _render_twiml_response(response)


@voice_router.post("/call-hospitals")
async def start_parallel_hospital_calls(payload: PatientInput, request: Request) -> dict[str, Any]:
    """Classify a patient and launch up to five parallel hospital voice calls."""
    database = _get_database(request)
    settings = _get_settings(request)

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

        top_hospitals = candidate_hospitals[:MAX_PARALLEL_HOSPITAL_CALLS]
        if not top_hospitals:
            return {
                "status": "skipped",
                "detail": "No hospitals were available to call.",
                "triage": triage.model_dump(),
                "session": None,
            }

        await database.ensure_voice_schema()

        session = VoiceCallSession(
            session_id=uuid4().hex,
            patient_payload=payload.model_dump(),
            patient_summary=triage.patient_summary,
            severity=triage.severity,
            department=triage.department,
            override_applied=override_applied,
            routing_reasoning=routing_preface + routing_reasoning,
            selected_hospital_id=selected_hospital.id if selected_hospital else None,
        )

        for index, hospital in enumerate(top_hospitals, start=1):
            phone_number = await _resolve_hospital_phone_number(database, hospital, index)
            session.hospitals[hospital.id] = VoiceCallHospitalState(
                hospital_id=hospital.id,
                hospital_name=hospital.name,
                phone_number=phone_number,
                eta_minutes=hospital.eta_minutes,
                distance_km=hospital.distance_km,
                score=hospital.score,
            )

        await _store_voice_session(session)

        if not _voice_calling_enabled(settings):
            for hospital in session.hospitals.values():
                hospital.call_status = "skipped"
                hospital.error = "Twilio credentials, BASE_URL, or caller number are not configured."

            return {
                "status": "skipped",
                "detail": "Twilio voice calling is not configured. No calls were placed.",
                "triage": triage.model_dump(),
                "session": _session_snapshot(session),
            }

        await asyncio.gather(
            *[_create_outbound_call(session.session_id, hospital, settings) for hospital in session.hospitals.values()],
            return_exceptions=True,
        )

        started_calls = any(hospital.call_sid for hospital in session.hospitals.values())
        return {
            "status": "started" if started_calls else "skipped",
            "detail": (
                "Parallel hospital voice calls started."
                if started_calls
                else "No outbound calls were started. Check hospital phone numbers."
            ),
            "triage": triage.model_dump(),
            "session": _session_snapshot(session),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to start hospital voice calls: {exc}") from exc


@voice_router.get("/session/{session_id}")
async def get_parallel_call_session(session_id: str) -> dict[str, Any]:
    """Return the live state of a previously started parallel hospital call batch."""
    session = await _get_voice_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Voice call session not found.")
    return _session_snapshot(session)


@voice_router.api_route("/twiml/{session_id}/{hospital_id}", methods=["GET", "POST"])
async def build_hospital_call_twiml(session_id: str, hospital_id: int) -> Response:
    """Serve the TwiML prompt that asks a hospital to confirm bed availability."""
    session = await _get_voice_session(session_id)
    if session is None:
        return _empty_twiml_message("This emergency triage request has expired. Goodbye.")

    hospital = session.hospitals.get(hospital_id)
    if hospital is None:
        return _empty_twiml_message("This emergency triage request is invalid. Goodbye.")

    if session.reserved_hospital_id and session.reserved_hospital_id != hospital_id:
        return _empty_twiml_message("A bed has already been reserved with another hospital. Goodbye.")

    hospital.call_status = "in-progress"

    response = VoiceResponse()
    gather = Gather(
        num_digits=1,
        action=f"{_normalized_base_url()}/api/voice/respond/{session_id}/{hospital_id}",
        method="POST",
        timeout=8,
        action_on_empty_result=True,
    )
    gather.say(_voice_prompt_for_hospital(session, hospital), voice="alice")
    response.append(gather)
    response.say("No input received. Goodbye.", voice="alice")
    response.hangup()
    return _render_twiml_response(response)


@voice_router.api_route("/respond/{session_id}/{hospital_id}", methods=["GET", "POST"])
async def handle_hospital_keypress(session_id: str, hospital_id: int, request: Request) -> Response:
    """Handle a hospital keypad response and reserve the bed when digit one is pressed."""
    session = await _get_voice_session(session_id)
    if session is None:
        return _empty_twiml_message("This emergency triage request has expired. Goodbye.")

    hospital = session.hospitals.get(hospital_id)
    if hospital is None:
        return _empty_twiml_message("This emergency triage request is invalid. Goodbye.")

    form_data = await _read_twilio_form(request)
    digits = form_data.get("Digits", "")
    call_sid = form_data.get("CallSid", "")
    if call_sid:
        hospital.call_sid = call_sid

    response = VoiceResponse()

    if digits == "1":
        reservation_result = await _reserve_bed_for_session(_get_database(request), session, hospital_id)
        hospital.response_digit = "1"

        if reservation_result == "reserved":
            hospital.call_status = "accepted"
            response.say(
                "Bed availability confirmed. The bed is now reserved. Please prepare for patient arrival. Goodbye.",
                voice="alice",
            )
            await _cancel_other_active_calls(session, hospital_id, _get_settings(request))
        elif reservation_result == "already_reserved":
            hospital.call_status = "late_accept"
            hospital.error = "Another hospital already reserved the bed for this patient."
            response.say(
                "A different hospital already confirmed and reserved the bed for this patient. Goodbye.",
                voice="alice",
            )
        else:
            hospital.call_status = "no_bed_available"
            hospital.error = "Bed reservation failed because no bed remained available."
            response.say(
                "We could not reserve the bed because no bed was available in the system. Goodbye.",
                voice="alice",
            )
    elif digits == "2":
        hospital.response_digit = "2"
        hospital.call_status = "declined"
        response.say("No bed available noted. Goodbye.", voice="alice")
    else:
        hospital.response_digit = digits or None
        hospital.call_status = "no_input" if not digits else "invalid_input"
        response.say("No valid input received. Goodbye.", voice="alice")

    response.hangup()
    return _render_twiml_response(response)


@voice_router.api_route("/status/{session_id}/{hospital_id}", methods=["GET", "POST"])
async def update_hospital_call_status(session_id: str, hospital_id: int, request: Request) -> dict[str, str]:
    """Capture Twilio status callbacks so the session reflects real call progress."""
    session = await _get_voice_session(session_id)
    if session is None:
        return {"status": "ignored"}

    hospital = session.hospitals.get(hospital_id)
    if hospital is None:
        return {"status": "ignored"}

    form_data = await _read_twilio_form(request)
    call_status = form_data.get("CallStatus", "")
    call_sid = form_data.get("CallSid", "")
    error_code = form_data.get("ErrorCode", "")
    error_message = form_data.get("ErrorMessage", "")
    answered_by = form_data.get("AnsweredBy", "")

    if call_sid:
        hospital.call_sid = call_sid
    if error_code:
        hospital.twilio_error_code = error_code
    if error_message:
        hospital.twilio_error_message = error_message
    if answered_by:
        hospital.answered_by = answered_by
    if call_status:
        if hospital.call_status not in {"accepted", "declined", "late_accept", "no_bed_available"}:
            hospital.call_status = call_status

    logger.info(
        "Twilio status callback session_id=%s hospital_id=%s call_sid=%s status=%s error_code=%s error_message=%s answered_by=%s",
        session_id,
        hospital_id,
        hospital.call_sid,
        hospital.call_status,
        hospital.twilio_error_code,
        hospital.twilio_error_message,
        hospital.answered_by,
    )

    return {"status": "ok"}
