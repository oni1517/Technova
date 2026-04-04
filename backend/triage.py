import time

from backend.models import PatientInput, TriageAssessment, TriageResult


SCENARIO_DEFINITIONS = {
    "cardiac_arrest": {
        "vitals_frames": [
            {"hr": 52, "bp_sys": 90, "bp_dia": 60, "spo2": 91, "rr": 22},
            {"hr": 48, "bp_sys": 85, "bp_dia": 55, "spo2": 89, "rr": 24},
            {"hr": 55, "bp_sys": 92, "bp_dia": 62, "spo2": 90, "rr": 23},
            {"hr": 44, "bp_sys": 82, "bp_dia": 52, "spo2": 87, "rr": 26},
        ],
        "triage_flags": {"icu": True, "ventilator": False, "specialist": "cardio"},
        "severity": "critical",
    },
    "stroke": {
        "vitals_frames": [
            {"hr": 88, "bp_sys": 162, "bp_dia": 100, "spo2": 94, "rr": 18},
            {"hr": 92, "bp_sys": 168, "bp_dia": 104, "spo2": 93, "rr": 19},
            {"hr": 86, "bp_sys": 158, "bp_dia": 98, "spo2": 94, "rr": 18},
            {"hr": 90, "bp_sys": 174, "bp_dia": 108, "spo2": 92, "rr": 20},
        ],
        "triage_flags": {"icu": True, "ventilator": False, "specialist": "neuro"},
        "severity": "high",
    },
    "head_trauma": {
        "vitals_frames": [
            {"hr": 98, "bp_sys": 148, "bp_dia": 92, "spo2": 93, "rr": 20},
            {"hr": 105, "bp_sys": 152, "bp_dia": 97, "spo2": 91, "rr": 22},
            {"hr": 112, "bp_sys": 155, "bp_dia": 100, "spo2": 90, "rr": 25},
            {"hr": 118, "bp_sys": 158, "bp_dia": 104, "spo2": 88, "rr": 27},
        ],
        "triage_flags": {"icu": True, "ventilator": True, "specialist": "neuro"},
        "severity": "critical",
    },
    "respiratory_distress": {
        "vitals_frames": [
            {"hr": 122, "bp_sys": 112, "bp_dia": 70, "spo2": 82, "rr": 32},
            {"hr": 128, "bp_sys": 108, "bp_dia": 68, "spo2": 78, "rr": 35},
            {"hr": 132, "bp_sys": 106, "bp_dia": 65, "spo2": 76, "rr": 37},
            {"hr": 126, "bp_sys": 110, "bp_dia": 70, "spo2": 80, "rr": 33},
        ],
        "triage_flags": {"icu": True, "ventilator": True, "specialist": "pulmo"},
        "severity": "critical",
    },
}

_frame_counters: dict[str, int] = {}

_SPECIALIST_TO_DEPARTMENT = {
    "cardio": "cardiology",
    "neuro": "neurology",
    "pulmo": "pulmonology",
    "trauma": "trauma",
}


def compute_severity(vitals: dict, chips: list[str]) -> dict:
    hr = vitals.get("hr", 80)
    spo2 = vitals.get("spo2", 98)
    rr = vitals.get("rr", 16)
    bp = vitals.get("bp_sys", 120)

    severity = "low"
    icu = False
    ventilator = False
    specialist = None

    if spo2 < 85:
        severity = "critical"
        icu = True
        ventilator = True
    elif spo2 < 92:
        severity = "high"
        icu = True

    if hr < 50 or hr > 130:
        severity = "critical"
        icu = True
    elif hr < 60 or hr > 110:
        if severity == "low":
            severity = "moderate"

    if rr > 30 or rr < 8:
        severity = "critical"
        icu = True
    elif rr > 24:
        if severity in ("low", "moderate"):
            severity = "high"

    if bp < 85:
        severity = "critical"
        icu = True
    elif bp > 160:
        if severity == "low":
            severity = "high"

    chip_map = {
        "Chest Pain": {"severity": "critical", "icu": True, "specialist": "cardio"},
        "Stroke Signs": {"severity": "high", "icu": True, "specialist": "neuro"},
        "Head Injury": {"severity": "critical", "icu": True, "specialist": "neuro"},
        "Respiratory Distress": {
            "severity": "critical",
            "icu": True,
            "ventilator": True,
            "specialist": "pulmo",
        },
        "Unconscious": {"severity": "critical", "icu": True},
        "Severe Bleeding": {"severity": "high", "specialist": "trauma"},
    }
    severity_order = ["low", "moderate", "high", "critical"]
    for chip in chips:
        if chip in chip_map:
            overrides = chip_map[chip]
            if severity_order.index(overrides.get("severity", severity)) > severity_order.index(severity):
                severity = overrides["severity"]
            if overrides.get("icu"):
                icu = True
            if overrides.get("ventilator"):
                ventilator = True
            if overrides.get("specialist"):
                specialist = overrides["specialist"]

    return {
        "severity": severity,
        "icu_required": icu,
        "ventilator_required": ventilator,
        "specialist": specialist,
    }


def get_current_vitals(session_id: str, scenario: str) -> dict:
    frames = SCENARIO_DEFINITIONS.get(scenario, SCENARIO_DEFINITIONS["cardiac_arrest"])["vitals_frames"]
    idx = _frame_counters.get(session_id, 0)
    vitals = frames[idx % len(frames)]
    _frame_counters[session_id] = idx + 1
    bp_str = f"{vitals['bp_sys']}/{vitals['bp_dia']}"
    return {**vitals, "bp": bp_str, "timestamp": time.time()}


def _department_from_triage(result: TriageResult) -> str:
    if result.specialist:
        return _SPECIALIST_TO_DEPARTMENT.get(result.specialist, "emergency")
    if result.icu_required:
        return "icu"
    return "emergency"


def _build_explanation(result: TriageResult, vitals: dict, chips: list[str]) -> list[str]:
    lines = [
        (
            f"Vitals trend shows HR {vitals['hr']} bpm, BP {vitals['bp_sys']}/{vitals['bp_dia']} mmHg, "
            f"SpO2 {vitals['spo2']}%, RR {vitals['rr']}/min."
        ),
        f"Rules-based severity engine classified this patient as {result.severity.upper()}.",
    ]
    if chips:
        lines.append(f"Triage modifiers applied from scene cues: {', '.join(chips)}.")
    if result.ventilator_required:
        lines.append("Respiratory compromise indicates ventilator-capable critical care support.")
    elif result.icu_required:
        lines.append("Escalation requires ICU-capable receiving support.")
    return lines[:4]


async def classify_patient(patient: PatientInput, _settings) -> TriageAssessment:
    vitals = patient.as_vitals_dict()
    computed = TriageResult(**compute_severity(vitals, patient.chips))
    department = _department_from_triage(computed)
    bp = f"{vitals['bp_sys']}/{vitals['bp_dia']}"

    return TriageAssessment(
        severity=computed.severity,
        department=department,
        explanation=_build_explanation(computed, vitals, patient.chips),
        patient_summary=(
            f"HR {vitals['hr']} bpm, BP {bp} mmHg, SpO2 {vitals['spo2']}%, "
            f"RR {vitals['rr']}/min, injury: {patient.injury.strip()}."
        ),
        source="fallback",
    )
