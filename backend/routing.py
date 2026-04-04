import asyncio

from backend.models import HospitalOption, HospitalRecord, PatientInput, TriageAssessment
from backend.utils import estimate_eta_minutes, haversine_distance_km, pretty_department


def calculateScore(
    hospital: HospitalRecord,
    required_spec: str,
    severity: str,
    *,
    time: float,
    distance: float,
) -> float:
    rating = hospital.rating or 3
    specialization = getattr(hospital, "specialization", None) or hospital.departments or []
    specialization_match = 1 if required_spec in specialization else 0
    available_value = getattr(hospital, "available", None)
    availability = 1 if (available_value if available_value is not None else hospital.available_beds > 0) else 0

    if severity == "critical":
        return (
            (time * 0.5)
            + (distance * 0.2)
            - (rating * 1.5)
            - (specialization_match * 25)
            - (availability * 15)
        )

    return (
        (distance * 0.3)
        + (time * 0.2)
        - (rating * 3)
        - (specialization_match * 10)
    )


async def _score_hospital(
    hospital: HospitalRecord,
    patient: PatientInput,
    required_spec: str,
    severity: str,
) -> HospitalOption:
    await asyncio.sleep(0)
    distance_km = haversine_distance_km(patient.patient_lat, patient.patient_lon, hospital.lat, hospital.lon)
    eta_minutes = estimate_eta_minutes(distance_km)
    specialization = getattr(hospital, "specialization", None) or hospital.departments or []
    specialization_match = required_spec in specialization
    available_value = getattr(hospital, "available", None)
    is_available = available_value if available_value is not None else hospital.available_beds > 0

    raw_score = calculateScore(
        hospital,
        required_spec,
        severity,
        time=eta_minutes,
        distance=distance_km,
    )
    display_score = 100 / (1 + abs(raw_score))

    routing_reason = (
        f"Triage score uses ETA {eta_minutes} min, distance {distance_km:.2f} km, "
        f"rating {hospital.rating:.1f}, specialization match {'yes' if specialization_match else 'no'}, "
        f"availability {'yes' if is_available else 'no'}."
    )

    return HospitalOption(
        **hospital.model_dump(),
        eta_minutes=eta_minutes,
        distance_km=round(distance_km, 2),
        raw_score=raw_score,
        display_score=display_score,
        routing_reason=routing_reason,
    )


async def select_best_hospital(
    patient: PatientInput,
    triage: TriageAssessment,
    hospitals: list[HospitalRecord],
) -> tuple[HospitalOption | None, list[HospitalOption], bool, list[str]]:
    if not hospitals:
        return None, [], False, ["No hospital records were available for triage scoring."]

    scored = await asyncio.gather(
        *[_score_hospital(hospital, patient, triage.department, triage.severity) for hospital in hospitals]
    )
    ranked = sorted(scored, key=lambda item: item.raw_score)
    selected = ranked[0]

    if triage.severity == "critical":
        reasoning = [
            f"Critical triage ranking prioritized ETA and specialization for {pretty_department(triage.department)}.",
            f"Hospitals were ranked by triage priority; {selected.name} ranked first.",
        ]
    else:
        reasoning = [
            f"Non-critical triage ranking prioritized rating for {pretty_department(triage.department)} while keeping time and distance in the score.",
            f"Hospitals were ranked by triage priority; {selected.name} ranked first.",
        ]

    return selected, ranked, False, reasoning

# Update function signature to accept scene_severity
async def route_patient(triage_data: dict, scene_severity: str = "MEDIUM"):
    # 1. Start with all available hospitals
    hospitals = await db.get_all_hospitals() 

    # 2. HIGH SEVERITY OVERRIDE
    # If severity is HIGH, we strictly filter for Level 1 Trauma Centers FIRST
    if scene_severity == "HIGH":
        hospitals = [h for h in hospitals if h.trauma_level == 1]
        
        # Fallback: If no Level 1s are available/online, revert to all to avoid 0 results
        if not hospitals:
            hospitals = await db.get_all_hospitals()

    # 3. Continue with existing distance/specialty filtering
    # ... (existing routing logic)