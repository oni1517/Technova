import asyncio
import math

import httpx
from twilio.rest import Client

from backend.config import Settings
from backend.models import HospitalOption, PatientInput, SMSDelivery, TriageAssessment, VoiceCallDelivery


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def estimate_eta_minutes(distance_km: float) -> int:
    average_city_speed_kmh = 28
    dispatch_buffer_minutes = 4
    travel_minutes = (distance_km / average_city_speed_kmh) * 60
    return max(4, round(travel_minutes + dispatch_buffer_minutes))


def pretty_department(department: str) -> str:
    return department.replace("_", " ").title()


def mask_phone_number(phone_number: str | None) -> str | None:
    if not phone_number:
        return None
    visible_suffix = phone_number[-4:]
    prefix = phone_number[: min(3, len(phone_number))]
    masked_length = max(0, len(phone_number) - len(prefix) - len(visible_suffix))
    return f"{prefix}{'*' * masked_length}{visible_suffix}"


def resolve_hospital_alert_number(hospital_name: str, settings: Settings) -> str | None:
    # For hackathon use, a shared demo destination number is enough and keeps setup minimal.
    return settings.twilio_to_number


def build_sms_body(
    patient: PatientInput,
    triage: TriageAssessment,
    hospital: HospitalOption,
) -> str:
    return (
        f"Golden Hour Alert | Severity: {triage.severity.upper()} | "
        f"Dept: {pretty_department(triage.department)} | ETA: {hospital.eta_minutes} min | "
        f"Patient: HR {patient.heart_rate}, BP {patient.systolic_bp}/{patient.diastolic_bp}, "
        f"SpO2 {patient.oxygen_saturation}, Injury: {patient.injury}"
    )


async def send_sms_alert(
    patient: PatientInput,
    triage: TriageAssessment,
    hospital: HospitalOption | None,
    settings: Settings,
) -> SMSDelivery:
    if hospital is None:
        return SMSDelivery(
            status="skipped",
            body="SMS skipped because no hospital was selected.",
            error="No hospital selected.",
        )

    body = build_sms_body(patient, triage, hospital)
    to_number = resolve_hospital_alert_number(hospital.name, settings)

    if not all(
        [
            settings.twilio_account_sid,
            settings.twilio_auth_token,
            settings.twilio_from_number,
            to_number,
        ]
    ):
        return SMSDelivery(
            status="skipped",
            to_number=to_number,
            body=body,
            error="Twilio credentials or destination number not configured.",
        )

    def _send_message() -> str:
        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)
        message = client.messages.create(
            body=body,
            from_=settings.twilio_from_number,
            to=to_number,
        )
        return message.sid

    try:
        sid = await asyncio.to_thread(_send_message)
        return SMSDelivery(status="sent", to_number=to_number, sid=sid, body=body)
    except Exception as exc:
        return SMSDelivery(
            status="failed",
            to_number=to_number,
            body=body,
            error=str(exc),
        )


async def queue_bolna_vobiz_call(
    patient: PatientInput,
    triage: TriageAssessment,
    hospital: HospitalOption | None,
    settings: Settings,
    recipient_phone_number: str | None = None,
) -> VoiceCallDelivery:
    provider = f"bolna_{settings.bolna_provider}"
    target_number = recipient_phone_number or settings.bolna_default_recipient_phone_number

    if hospital is None:
        return VoiceCallDelivery(
            status="skipped",
            provider=provider,
            recipient_phone_number=target_number,
            message="Voice call skipped because no hospital was selected.",
            error="No hospital selected.",
        )

    if not all([settings.bolna_api_key, settings.bolna_agent_id, target_number]):
        return VoiceCallDelivery(
            status="skipped",
            provider=provider,
            recipient_phone_number=target_number,
            message="Bolna call not queued.",
            error="Bolna API key, agent ID, or recipient phone number not configured.",
        )

    payload = {
        "agent_id": settings.bolna_agent_id,
        "recipient_phone_number": target_number,
        "user_data": {
            "severity": triage.severity,
            "department": pretty_department(triage.department),
            "patient_summary": triage.patient_summary,
            "injury": patient.injury.strip(),
            "selected_hospital": hospital.name,
            "hospital_eta_minutes": str(hospital.eta_minutes),
        },
    }
    if settings.bolna_from_phone_number:
        payload["from_phone_number"] = settings.bolna_from_phone_number

    headers = {
        "Authorization": f"Bearer {settings.bolna_api_key}",
        "Content-Type": "application/json",
    }

    async def _post_call(call_payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(settings.bolna_api_url, headers=headers, json=call_payload)
            response.raise_for_status()
            return response.json()

    try:
        data = await _post_call(payload)

        api_status = data.get("status")
        status = api_status if api_status in {"queued", "failed"} else "queued"
        return VoiceCallDelivery(
            status=status,
            provider=provider,
            recipient_phone_number=target_number,
            execution_id=data.get("execution_id"),
            message=data.get("message", "Bolna call queued."),
            error=None,
        )
    except httpx.HTTPStatusError as exc:
        error_text = exc.response.text.strip() or str(exc)

        # Some Bolna agents are backed by a different telephony provider than the
        # configured caller ID. Retry once without an explicit from_number so the
        # agent can fall back to its default provider-side number.
        if "from_number doesn't exist" in error_text and "from_phone_number" in payload:
            fallback_payload = dict(payload)
            fallback_payload.pop("from_phone_number", None)
            try:
                data = await _post_call(fallback_payload)
                api_status = data.get("status")
                status = api_status if api_status in {"queued", "failed"} else "queued"
                return VoiceCallDelivery(
                    status=status,
                    provider=provider,
                    recipient_phone_number=target_number,
                    execution_id=data.get("execution_id"),
                    message=data.get("message", "Bolna call queued."),
                    error="Configured from_phone_number was rejected; used agent default caller instead.",
                )
            except httpx.HTTPStatusError as retry_exc:
                error_text = retry_exc.response.text.strip() or str(retry_exc)

        return VoiceCallDelivery(
            status="failed",
            provider=provider,
            recipient_phone_number=target_number,
            message="Bolna call failed.",
            error=error_text,
        )
    except Exception as exc:
        return VoiceCallDelivery(
            status="failed",
            provider=provider,
            recipient_phone_number=target_number,
            message="Bolna call failed.",
            error=str(exc),
        )
