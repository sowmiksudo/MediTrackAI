import uuid
from sqlalchemy import (
    Boolean,
    Column,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pgvector.sqlalchemy import HALFVEC

from db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone_e164 = Column(String(32), unique=True, nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profiles = relationship("PatientProfile", back_populates="owner", cascade="all, delete-orphan")


class PatientProfile(Base):
    __tablename__ = "patient_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name = Column(String(120), nullable=False)
    relationship_type = Column("relationship", String(40), nullable=False, default="self")
    date_of_birth = Column(Date, nullable=True)
    sex = Column(String(16), nullable=True)  # M | F | Other
    chronic_conditions = Column(JSONB, nullable=False, default=list)
    allergies = Column(JSONB, nullable=False, default=list)
    emergency_contact_phone = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    owner = relationship("User", back_populates="profiles")


class PdpaConsent(Base):
    __tablename__ = "pdpa_consents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    consent_version = Column(String(32), nullable=False, default="bd-pdpa-2026-v1")
    accepted_local_storage = Column(Boolean, nullable=False, default=True)
    accepted_cloud_ai_processing = Column(Boolean, nullable=False, default=True)
    accepted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    audio_path = Column(String(512), nullable=True)
    transcript = Column(JSONB, nullable=True)
    pii_redacted_transcript = Column(JSONB, nullable=True)
    summary = Column(Text, nullable=True)
    mood = Column(String(64), nullable=True)
    symptoms = Column(JSONB, nullable=False, default=list)
    medications_mentioned = Column(JSONB, nullable=False, default=list)
    sleep_quality = Column(String(64), nullable=True)
    energy_level = Column(String(64), nullable=True)
    concerns = Column(JSONB, nullable=False, default=list)
    ai_insights = Column(JSONB, nullable=False, default=list)
    red_flags_detected = Column(JSONB, nullable=False, default=list)
    overall_score = Column(String(16), nullable=False, default="neutral")  # positive | neutral | negative
    language_detected = Column(String(32), nullable=True, default="bn-en")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class Prescription(Base):
    __tablename__ = "prescriptions"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(512), nullable=False)
    doc_date = Column(String(32), nullable=True)
    doctor_name = Column(String(255), nullable=True)
    doctor_qualification = Column(String(255), nullable=True)
    doctor_bmdc_reg = Column(String(64), nullable=True)
    hospital = Column(String(255), nullable=True)
    diagnosis = Column(Text, nullable=True)
    raw_ocr_text = Column(Text, nullable=True)
    extracted_json = Column(JSONB, nullable=True)
    verification_status = Column(String(32), nullable=False, default="pending_review")  # pending_review | confirmed
    overall_confidence = Column(Float, nullable=True)
    ddi_alerts = Column(JSONB, nullable=False, default=list)
    prescription_summary = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String(512), nullable=False)
    lab_name = Column(String(255), nullable=True)
    report_date = Column(String(32), nullable=True)
    raw_ocr_text = Column(Text, nullable=True)
    extracted_json = Column(JSONB, nullable=True)
    verification_status = Column(String(32), nullable=False, default="confirmed")
    critical_alerts = Column(JSONB, nullable=False, default=list)
    lab_summary_overview = Column(Text, nullable=True)
    deterministic_scores = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class DoctorBrief(Base):
    __tablename__ = "doctor_briefs"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    pdf_file_path = Column(String(512), nullable=True)
    share_token_hash = Column(String(128), unique=True, nullable=True, index=True)
    share_expires_at = Column(DateTime(timezone=True), nullable=True)
    brief_payload = Column(JSONB, nullable=False, default=dict)
    deterministic_scores = Column(JSONB, nullable=False, default=dict)
    citations = Column(JSONB, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class BackgroundJob(Base):
    __tablename__ = "background_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    job_type = Column(String(32), nullable=False)  # rx_parse | lab_parse | brief_gen | reindex
    status = Column(String(32), nullable=False, default="queued")  # queued | running | completed | failed
    progress_pct = Column(Integer, nullable=False, default=0)
    current_step = Column(String(128), nullable=False, default="Queued")
    result_id = Column(String(64), nullable=True)
    result_payload = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class BdDrugCatalog(Base):
    __tablename__ = "bd_drug_catalog"
    __table_args__ = (
        UniqueConstraint("brand_name", "strength", "dosage_form", name="uq_bd_drug_brand_strength_form"),
        Index("ix_bd_drug_brand_trgm", "brand_name", postgresql_using="gin", postgresql_ops={"brand_name": "gin_trgm_ops"}),
        Index("ix_bd_drug_generic_trgm", "generic_name", postgresql_using="gin", postgresql_ops={"generic_name": "gin_trgm_ops"}),
    )

    id = Column(Integer, primary_key=True, index=True)
    brand_name = Column(String(160), nullable=False)
    generic_name = Column(String(200), nullable=False)
    strength = Column(String(80), nullable=False, default="")
    dosage_form = Column(String(80), nullable=False, default="Tablet")
    manufacturer = Column(String(160), nullable=True)
    indicative_price_bdt = Column(Float, nullable=True)
    atc_code = Column(String(32), nullable=True)
    drug_class = Column(String(120), nullable=True)


class BdDdiRule(Base):
    __tablename__ = "bd_ddi_rules"
    __table_args__ = (
        UniqueConstraint("drug_a_generic", "drug_b_generic", "rule_type", name="uq_bd_ddi_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    drug_a_generic = Column(String(160), nullable=False, index=True)
    drug_b_generic = Column(String(160), nullable=False, index=True)
    rule_type = Column(String(32), nullable=False)  # duplicate_class | major_ddi | moderate_ddi
    severity = Column(String(16), nullable=False)  # critical | warning | info
    clinical_note = Column(Text, nullable=False)


class LoincLabReference(Base):
    __tablename__ = "loinc_lab_reference"

    loinc_code = Column(String(32), primary_key=True)
    canonical_name = Column(String(160), nullable=False, index=True)
    aliases = Column(ARRAY(String), nullable=False, default=list)
    standard_unit = Column(String(32), nullable=False)
    alt_units = Column(JSONB, nullable=False, default=dict)  # e.g. {"mg/dL": {"op": "div", "factor": 18.0182}}
    ref_low_male = Column(Float, nullable=True)
    ref_high_male = Column(Float, nullable=True)
    ref_low_female = Column(Float, nullable=True)
    ref_high_female = Column(Float, nullable=True)
    critical_low = Column(Float, nullable=True)
    critical_high = Column(Float, nullable=True)


class ClinicalObservation(Base):
    __tablename__ = "clinical_observations"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # lab | checkin
    source_id = Column(Integer, nullable=False)
    loinc_code = Column(String(32), ForeignKey("loinc_lab_reference.loinc_code", ondelete="SET NULL"), nullable=True, index=True)
    raw_name = Column(String(160), nullable=False)
    raw_value = Column(String(64), nullable=False)
    raw_unit = Column(String(32), nullable=True)
    canonical_value = Column(Float, nullable=True)
    canonical_unit = Column(String(32), nullable=True)
    reference_range = Column(String(80), nullable=True)
    flag = Column(String(16), nullable=False, default="normal")  # low | normal | high | critical
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)


class MedicationEpisode(Base):
    __tablename__ = "medication_episodes"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id", ondelete="CASCADE"), nullable=True, index=True)
    raw_brand_name = Column(String(160), nullable=False)
    matched_drug_id = Column(Integer, ForeignKey("bd_drug_catalog.id", ondelete="SET NULL"), nullable=True)
    generic_name = Column(String(200), nullable=True)
    drug_class = Column(String(120), nullable=True)
    dosage = Column(String(80), nullable=True)
    frequency_bd = Column(String(80), nullable=True)  # e.g. "1+0+1"
    duration_days = Column(Integer, nullable=True)
    special_instructions = Column(String(255), nullable=True)
    match_confidence = Column(Float, nullable=False, default=0.0)
    needs_user_confirm = Column(Boolean, nullable=False, default=True)
    status = Column(String(24), nullable=False, default="active")  # active | completed | stopped
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)


class ClinicalEdge(Base):
    __tablename__ = "clinical_edges"

    id = Column(Integer, primary_key=True, index=True)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    src_type = Column(String(32), nullable=False)
    src_id = Column(String(64), nullable=False)
    edge_type = Column(String(48), nullable=False)  # PRESCRIBED_FOR | TRIGGERED_ALERT | FOLLOW_UP_OF | DUPLICATE_OF
    dst_type = Column(String(32), nullable=False)
    dst_id = Column(String(64), nullable=False)
    edge_metadata = Column("metadata", JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_kc_tsv_gin", "tsv", postgresql_using="gin"),
        Index(
            "ix_kc_bge_m3_hnsw",
            "embedding_bge_m3",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_bge_m3": "halfvec_cosine_ops"},
        ),
        Index(
            "ix_kc_gemini_mm_hnsw",
            "embedding_gemini_mm",
            postgresql_using="hnsw",
            postgresql_ops={"embedding_gemini_mm": "halfvec_cosine_ops"},
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_profile_id = Column(UUID(as_uuid=True), ForeignKey("patient_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)  # checkin | prescription | lab_report | medication | observation
    source_id = Column(String(64), nullable=False)
    chunk_text = Column(Text, nullable=False)
    language = Column(String(24), nullable=False, default="en")
    event_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    chunk_metadata = Column(JSONB, nullable=False, default=dict)
    tsv = Column(TSVECTOR, Computed("to_tsvector('english', chunk_text)", persisted=True), nullable=False)
    embedding_bge_m3 = Column(HALFVEC(1024), nullable=True)
    embedding_gemini_mm = Column(HALFVEC(1536), nullable=True)
    bge_sparse_weights = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
