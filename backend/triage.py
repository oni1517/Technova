import logging

import httpx

from backend.config import Settings
from backend.models import DepartmentName, PatientInput, TriageAssessment

logger = logging.getLogger(__name__)


TRIAGE_TOOL_SCHEMA = {
    "name": "record_triage",
    "description": (
        "Return a conservative emergency triage assessment for ambulance routing. "
        "Choose the most appropriate receiving department and concise clinical reasoning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "severity": {
                "type": "string",
                "enum": ["critical", "high", "moderate", "low"],
            },
            "department": {
                "type": "string",
                "enum": [
                    "emergency",
                    "trauma",
                    "cardiology",
                    "neurology",
                    "orthopedics",
                    "pulmonology",
                    "general_surgery",
                    "icu",
                ],
            },
            "explanation": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 4,
            },
            "patient_summary": {
                "type": "string",
            },
        },
        "required": ["severity", "department", "explanation", "patient_summary"],
    },
}


def _pick_department(injury: str, oxygen_saturation: int) -> DepartmentName:
    injury_text = injury.lower()

    if any(word in injury_text for word in ["chest pain", "cardiac", "heart", "palpitation"]):
        return "cardiology"
    if any(word in injury_text for word in ["stroke", "seizure", "head", "brain", "unconscious"]):
        return "neurology"
    if any(word in injury_text for word in ["fracture", "bone", "spine", "limb"]):
        return "orthopedics"
    if any(word in injury_text for word in ["accident", "collision", "bleeding", "wound", "burn", "trauma"]):
        return "trauma"
    if oxygen_saturation <= 92 or any(word in injury_text for word in ["breath", "asthma", "lung", "respiratory"]):
        return "pulmonology"
    if any(word in injury_text for word in ["abdomen", "stomach", "appendix", "surgery"]):
        return "general_surgery"
    return "emergency"


def fallback_triage(patient: PatientInput) -> TriageAssessment:
    injury_text = patient.injury.lower()
    department = _pick_department(patient.injury, patient.oxygen_saturation)

    critical_keywords = {
        "unconscious",
        "stroke",
        "cardiac arrest",
        "severe bleeding",
        "major burn",
        "breathing",
        "collapse",
        "seizure",
        "gunshot",
        "stabbing",
    }
    high_keywords = {
        "fracture",
        "head injury",
        "chest pain",
        "shortness of breath",
        "crush injury",
        "road accident",
    }

    if (
        patient.oxygen_saturation <= 88
        or patient.systolic_bp < 90
        or patient.heart_rate >= 140
        or any(keyword in injury_text for keyword in critical_keywords)
    ):
        severity = "critical"
        explanation = [
            "Vitals indicate immediate hemodynamic or respiratory instability.",
            "Routing should heavily prioritize faster arrival and the closest specialization fit.",
        ]
    elif (
        patient.oxygen_saturation <= 92
        or patient.systolic_bp < 100
        or patient.heart_rate >= 120
        or any(keyword in injury_text for keyword in high_keywords)
    ):
        severity = "high"
        explanation = [
            "Patient shows significant physiological stress and needs urgent specialist review.",
            "Routing should favor faster transfer while keeping department fit strong.",
        ]
    elif patient.oxygen_saturation <= 95 or patient.heart_rate >= 105:
        severity = "moderate"
        explanation = [
            "Patient is symptomatic but not currently in immediate collapse.",
            "Routing can lean on rating while still considering travel time and specialization fit.",
        ]
    else:
        severity = "low"
        explanation = [
            "Vitals are comparatively stable at intake.",
            "Standard emergency routing is acceptable unless symptoms worsen.",
        ]

    patient_summary = (
        f"HR {patient.heart_rate} bpm, BP {patient.systolic_bp}/{patient.diastolic_bp} mmHg, "
        f"SpO2 {patient.oxygen_saturation}%, injury: {patient.injury.strip()}."
    )

    return TriageAssessment(
        severity=severity,
        department=department,
        explanation=explanation,
        patient_summary=patient_summary,
        source="fallback",
    )


async def classify_patient(patient: PatientInput, settings: Settings) -> TriageAssessment:
    if not settings.anthropic_api_key:
        return fallback_triage(patient)

    prompt = (
        "Classify this ambulance intake for hospital routing in Pune.\n"
        f"Heart rate: {patient.heart_rate} bpm\n"
        f"Blood pressure: {patient.systolic_bp}/{patient.diastolic_bp} mmHg\n"
        f"Oxygen saturation: {patient.oxygen_saturation}%\n"
        f"Injury/complaint: {patient.injury}\n"
        "Be clinically conservative. Use the provided tool to return the assessment."
    )

    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 300,
        "temperature": 0,
        "system": (
            "You are an emergency triage copilot for ambulance dispatch. "
            "Return only a structured triage classification using the provided tool."
        ),
        "messages": [{"role": "user", "content": prompt}],
        "tools": [TRIAGE_TOOL_SCHEMA],
        "tool_choice": {"type": "tool", "name": "record_triage"},
    }

    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(settings.anthropic_api_url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        content_blocks = data.get("content", [])
        tool_block = next(
            (
                block
                for block in content_blocks
                if block.get("type") == "tool_use" and block.get("name") == "record_triage"
            ),
            None,
        )

        if not tool_block or "input" not in tool_block:
            raise ValueError("Anthropic response did not include the expected tool output.")

        structured_output = tool_block["input"]
        return TriageAssessment(
            severity=structured_output["severity"],
            department=structured_output["department"],
            explanation=structured_output["explanation"],
            patient_summary=structured_output["patient_summary"],
            source="anthropic",
        )
    except Exception as exc:
        logger.exception("Anthropic triage failed. Falling back to rules-based triage. Error: %s", exc)
        return fallback_triage(patient)

