import asyncio

from backend.config import Settings
from backend.models import HospitalOption, HospitalRecord, PatientInput, TriageAssessment
from backend.utils import estimate_eta_minutes, haversine_distance_km, pretty_department


async def _score_hospital(
    hospital: HospitalRecord,
    patient: PatientInput,
    department: str,
    settings: Settings,
) -> HospitalOption:
    await asyncio.sleep(0)
    distance_km = haversine_distance_km(patient.patient_lat, patient.patient_lon, hospital.lat, hospital.lon)
    eta_minutes = estimate_eta_minutes(distance_km)

    eta_component = max(0.0, 1 - min(eta_minutes, 45) / 45)
    bed_component = min(hospital.available_beds, 20) / 20
    department_component = 1.0 if department in hospital.departments else 0.0

    score = (
        eta_component * settings.eta_weight
        + bed_component * settings.bed_weight
        + department_component * settings.department_weight
    )

    routing_reason = (
        f"Weighted score {score:.3f} from ETA {eta_minutes} min, "
        f"{hospital.available_beds} open beds, "
        f"department match {'yes' if department_component else 'no'}."
    )

    return HospitalOption(
        **hospital.model_dump(),
        eta_minutes=eta_minutes,
        distance_km=round(distance_km, 2),
        score=round(score, 3),
        routing_reason=routing_reason,
    )


async def select_best_hospital(
    patient: PatientInput,
    triage: TriageAssessment,
    hospitals: list[HospitalRecord],
    settings: Settings,
) -> tuple[HospitalOption | None, list[HospitalOption], bool, list[str]]:
    if not hospitals:
        return None, [], False, ["No hospital records matched the current routing filters."]

    if triage.severity == "critical":
        icu_hospitals = [hospital for hospital in hospitals if hospital.icu_available]
        active_pool = icu_hospitals or hospitals
        scored = await asyncio.gather(
            *[_score_hospital(hospital, patient, triage.department, settings) for hospital in active_pool]
        )
        ranked = sorted(scored, key=lambda item: item.eta_minutes)
        selected = ranked[0]
        reasoning = [
            "Critical override applied: nearest ICU-capable hospital takes precedence over weighted scoring.",
            f"Selected {selected.name} because it has the fastest projected arrival at {selected.eta_minutes} minutes.",
        ]
        if not icu_hospitals:
            reasoning.append("No ICU-marked hospitals were available, so the nearest fallback hospital was used.")
        return selected, ranked, True, reasoning

    scored = await asyncio.gather(
        *[_score_hospital(hospital, patient, triage.department, settings) for hospital in hospitals]
    )
    ranked = sorted(scored, key=lambda item: item.score, reverse=True)
    selected = ranked[0]

    reasoning = [
        f"Department filter applied for {pretty_department(triage.department)}.",
        "Hospitals ranked using weighted ETA, bed availability, and department fit.",
        f"Selected {selected.name} with score {selected.score:.3f} and ETA {selected.eta_minutes} minutes.",
    ]

    return selected, ranked, False, reasoning

