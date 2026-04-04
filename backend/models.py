from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SeverityLevel = Literal["critical", "high", "moderate", "low"]
DepartmentName = Literal[
    "emergency",
    "trauma",
    "cardiology",
    "neurology",
    "orthopedics",
    "pulmonology",
    "general_surgery",
    "icu",
]
ScenarioName = Literal["cardiac_arrest", "stroke", "head_trauma", "respiratory_distress"]


class Coordinate(BaseModel):
    lat: float
    lon: float


class VitalsFrame(BaseModel):
    hr: int
    bp_sys: int
    bp_dia: int
    bp: str
    spo2: int
    rr: int
    timestamp: float


class TriageResult(BaseModel):
    severity: Literal["low", "moderate", "high", "critical"]
    icu_required: bool
    ventilator_required: bool
    specialist: Optional[str] = None


class PatientInput(BaseModel):
    hr: int = Field(..., ge=20, le=250)
    bp_sys: int = Field(..., ge=40, le=300)
    bp_dia: int = Field(..., ge=20, le=200)
    spo2: int = Field(..., ge=40, le=100)
    rr: int = Field(..., ge=1, le=80)
    injury: str = Field(..., min_length=3, max_length=400)
    scenario: ScenarioName = "cardiac_arrest"
    chips: list[str] = Field(default_factory=list)
    patient_lat: float = Field(default=18.5204, ge=-90, le=90)
    patient_lon: float = Field(default=73.8567, ge=-180, le=180)

    @property
    def heart_rate(self) -> int:
        return self.hr

    @property
    def systolic_bp(self) -> int:
        return self.bp_sys

    @property
    def diastolic_bp(self) -> int:
        return self.bp_dia

    @property
    def oxygen_saturation(self) -> int:
        return self.spo2

    def as_vitals_dict(self) -> dict:
        return {
            "hr": self.hr,
            "bp_sys": self.bp_sys,
            "bp_dia": self.bp_dia,
            "spo2": self.spo2,
            "rr": self.rr,
        }


class VoiceCallInput(PatientInput):
    recipient_phone_number: str | None = Field(default=None, min_length=8, max_length=20)


class TriageAssessment(BaseModel):
    severity: SeverityLevel
    department: DepartmentName
    explanation: list[str] = Field(default_factory=list)
    patient_summary: str
    source: Literal["anthropic", "fallback"]


class HospitalRecord(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    lat: float
    lon: float
    departments: list[str]
    available_beds: int
    icu_available: bool
    rating: float = 3.0


class HospitalOption(HospitalRecord):
    eta_minutes: int
    distance_km: float
    raw_score: float
    display_score: float
    routing_reason: str


class SMSDelivery(BaseModel):
    status: Literal["sent", "skipped", "failed"]
    to_number: str | None = None
    sid: str | None = None
    body: str
    error: str | None = None


class VoiceCallDelivery(BaseModel):
    status: Literal["queued", "skipped", "failed"]
    provider: str
    recipient_phone_number: str | None = None
    execution_id: str | None = None
    message: str
    error: str | None = None


class RouteMap(BaseModel):
    patient: Coordinate
    destination: Coordinate | None = None
    polyline: list[Coordinate] = Field(default_factory=list)


class TriageResponse(BaseModel):
    triage: TriageAssessment
    override_applied: bool
    selected_hospital: HospitalOption | None = None
    candidate_hospitals: list[HospitalOption] = Field(default_factory=list)
    routing_reasoning: list[str] = Field(default_factory=list)
    sms: SMSDelivery
    voice_call: VoiceCallDelivery | None = None
    map_data: RouteMap


class TriageRequest(BaseModel):
    scene_severity: Optional[str] = "MEDIUM"
