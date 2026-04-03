import asyncio
import math

from twilio.rest import Client

from backend.config import Settings
from backend.models import HospitalOption, PatientInput, SMSDelivery, TriageAssessment


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

