from typing import Literal

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


class Coordinate(BaseModel):
    lat: float
    lon: float


class PatientInput(BaseModel):
    heart_rate: int = Field(..., ge=20, le=250)
    systolic_bp: int = Field(..., ge=40, le=300)
    diastolic_bp: int = Field(..., ge=20, le=200)
    oxygen_saturation: int = Field(..., ge=40, le=100)
    injury: str = Field(..., min_length=3, max_length=400)
    patient_lat: float = Field(default=18.5204, ge=-90, le=90)
    patient_lon: float = Field(default=73.8567, ge=-180, le=180)


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


class HospitalOption(HospitalRecord):
    eta_minutes: int
    distance_km: float
    score: float
    routing_reason: str


class SMSDelivery(BaseModel):
    status: Literal["sent", "skipped", "failed"]
    to_number: str | None = None
    sid: str | None = None
    body: str
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
    map_data: RouteMap

