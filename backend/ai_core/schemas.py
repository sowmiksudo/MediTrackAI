from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class ExtractedMedicine(BaseModel):
    name: str
    dosage: Optional[str] = ""
    frequency: Optional[str] = ""  # Supports BD notation e.g. "1+0+1"
    duration: Optional[str] = ""
    special_instructions: Optional[str] = ""


class RxExtractionResult(BaseModel):
    doctor_name: Optional[str] = None
    doctor_qualification: Optional[str] = None
    doctor_bmdc_reg: Optional[str] = None
    hospital: Optional[str] = None
    prescription_date: Optional[str] = None
    patient_name: Optional[str] = None
    diagnosis: Optional[str] = None
    symptoms: Optional[str] = None
    advice: Optional[str] = None
    follow_up: Optional[str] = None
    medicines: List[ExtractedMedicine] = Field(default_factory=list)
    prescription_summary: str = ""
    raw_ocr_text: str = ""


class ExtractedLabMetric(BaseModel):
    test_name: str
    value: Optional[str] = None
    unit: Optional[str] = None
    reference_range: Optional[str] = None


class LabExtractionResult(BaseModel):
    lab_name: Optional[str] = None
    report_date: Optional[str] = None
    metrics: List[ExtractedLabMetric] = Field(default_factory=list)
    lab_summary_overview: str = ""
    raw_ocr_text: str = ""


class CheckInSummaryOutput(BaseModel):
    summary: str
    mood: str = "Neutral"
    symptoms: List[str] = Field(default_factory=list)
    medications_taken: List[str] = Field(default_factory=list)
    sleep_quality: str = "Unknown"
    energy_level: str = "Moderate"
    concerns: List[str] = Field(default_factory=list)
    ai_insights: List[str] = Field(default_factory=list)
    overall_score: Literal["positive", "neutral", "negative"] = "neutral"
    language_detected: str = "bn-en"


class BriefTimelineEvent(BaseModel):
    date: str
    event_type: str
    summary: str
    citation: str


class BriefMedicationItem(BaseModel):
    brand_name: str
    generic_name: Optional[str] = None
    dosage: Optional[str] = None
    frequency_bd: Optional[str] = None
    status: str = "active"
    flag: Optional[str] = None


class DoctorBriefOutput(BaseModel):
    patient_snapshot: str
    chief_concerns_summary: str
    timeline_events: List[BriefTimelineEvent] = Field(default_factory=list)
    lab_trends_narrative: str
    active_medications: List[BriefMedicationItem] = Field(default_factory=list)
    clinical_observations: List[str] = Field(default_factory=list)
    questions_for_doctor: List[str] = Field(default_factory=list)
    red_flag_summary: List[str] = Field(default_factory=list)
    disclaimer: str = (
        "Non-diagnostic clinical summary prepared by MediTrackAI for physician review. "
        "Confirm all medications, dosages, and diagnostic conclusions clinically."
    )


class RetrievalHit(BaseModel):
    chunk_id: str
    source_type: str
    source_id: str
    citation: str
    chunk_text: str
    event_at: str
    vec_score: float = 0.0
    bm25_score: float = 0.0
    trgm_score: float = 0.0
    rrf_score: float = 0.0
    temporal_decay: float = 1.0
    rerank_score: float = 0.0
    final_score: float = 0.0


class RetrievalTrace(BaseModel):
    query: str
    expanded_query: str
    embedding_backend: str
    reranker_backend: str
    latency_ms: float
    hits: List[RetrievalHit] = Field(default_factory=list)


class PiiRedactionResult(BaseModel):
    raw_text: str
    redacted_text: str
    engine: str
    entities_masked: List[str] = Field(default_factory=list)
    latency_ms: float = 0.0
