import asyncio
from datetime import datetime, timedelta, timezone
import os
import secrets
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.pipelines.rx_pipeline import _update_job
from ai_core.router import get_ai_provider
from ai_core.schemas import BriefMedicationItem, BriefTimelineEvent, DoctorBriefOutput
from auth.security import hash_share_token
from clinical.drug_verifier import check_ddi_and_duplicates
from clinical.red_flag_gate import evaluate_lab_red_flags
from clinical.risk_calculators import compute_age_years, compute_deterministic_clinical_scores
from db.models import CheckIn, ClinicalObservation, DoctorBrief, MedicationEpisode, PatientProfile, Prescription, Report
from utils.pdf_generator import generate_doctor_brief_pdf


class _CombinedBriefNarrative(BaseModel):
    patient_snapshot: str
    chief_concerns_summary: str
    timeline_events: List[BriefTimelineEvent] = Field(default_factory=list)
    lab_trends_narrative: str
    clinical_observations: List[str] = Field(default_factory=list)
    questions_for_doctor: List[str] = Field(default_factory=list)


def _build_deterministic_fallback_narrative(
    profile: PatientProfile,
    checkins: List[CheckIn],
    prescriptions: List[Prescription],
    obs_list_for_pdf: List[Dict[str, Any]],
    det_scores: Dict[str, Any],
    ddi_alerts: List[Dict[str, Any]],
) -> _CombinedBriefNarrative:
    events: List[BriefTimelineEvent] = []
    for c in checkins[:3]:
        d = c.created_at.strftime("%Y-%m-%d") if c.created_at else "Recent"
        events.append(
            BriefTimelineEvent(
                date=d,
                event_type="check_in",
                summary=c.summary or "Voice check-in recorded.",
                citation=f"[CheckIn #{c.id}]",
            )
        )
    for p in prescriptions[:3]:
        d = p.doc_date or (p.created_at.strftime("%Y-%m-%d") if p.created_at else "Recent")
        events.append(
            BriefTimelineEvent(
                date=d,
                event_type="prescription",
                summary=p.prescription_summary or f"Prescription from {p.doctor_name or 'doctor'}",
                citation=f"[Rx #{p.id}]",
            )
        )
    events.sort(key=lambda e: e.date, reverse=True)

    abnormal = [o for o in obs_list_for_pdf if o.get("flag") in ("high", "low", "critical")]
    lab_obs_bullets = [
        f"{o['canonical_name']}: {o['canonical_value']} {o['canonical_unit']} ({o['flag'].upper()} on {o['observed_date']})"
        for o in abnormal[:5]
    ]
    egfr = det_scores.get("egfr_ckd_epi", {})
    if egfr.get("status") == "computed":
        lab_obs_bullets.append(f"CKD-EPI eGFR: {egfr['egfr_ml_min']} mL/min/1.73m2 ({egfr['kdigo_stage']})")

    questions = []
    for a in ddi_alerts[:2]:
        questions.append(f"Review potential interaction/duplication: {', '.join(a.get('drugs', []))} ({a.get('rule_type')}).")
    if egfr.get("status") == "computed" and egfr.get("metformin_caution"):
        questions.append(f"Confirm renal dose adjustments given eGFR {egfr['egfr_ml_min']} mL/min.")
    if not questions:
        questions.append("Review current symptom trends and confirm continuation of active medications.")

    return _CombinedBriefNarrative(
        patient_snapshot=(
            f"{profile.display_name} ({profile.sex or 'N/A'}) managing {', '.join(profile.chronic_conditions or []) or 'general care'}. "
            f"Summary assembled from {len(obs_list_for_pdf)} normalized lab records, {len(prescriptions)} prescriptions, and {len(checkins)} check-ins."
        ),
        chief_concerns_summary=(checkins[0].summary if checkins else "No recent voice check-in concerns logged."),
        timeline_events=events[:5],
        lab_trends_narrative=(
            "Abnormal normalized lab markers noted: " + "; ".join(lab_obs_bullets[:4])
            if lab_obs_bullets
            else "All recorded lab markers are within reference ranges."
        ),
        clinical_observations=lab_obs_bullets or ["No abnormal laboratory trends flagged."],
        questions_for_doctor=questions,
    )


async def run_brief_dag(
    db: Session,
    patient_profile_id: Any,
    job_id: Optional[Any] = None,
    public_base_url: str = "http://localhost:8080",
) -> Dict[str, Any]:
    profile = db.query(PatientProfile).filter(PatientProfile.id == patient_profile_id).first()
    if not profile:
        raise ValueError("Patient profile not found")

    if job_id:
        _update_job(db, job_id, "running", 15, "Collecting longitudinal labs, BD meds & Bangla check-ins")

    checkins = (
        db.query(CheckIn)
        .filter(CheckIn.patient_profile_id == profile.id)
        .order_by(desc(CheckIn.created_at))
        .limit(8)
        .all()
    )
    prescriptions = (
        db.query(Prescription)
        .filter(Prescription.patient_profile_id == profile.id)
        .order_by(desc(Prescription.created_at))
        .limit(8)
        .all()
    )
    reports = (
        db.query(Report)
        .filter(Report.patient_profile_id == profile.id)
        .order_by(desc(Report.created_at))
        .limit(8)
        .all()
    )
    meds = (
        db.query(MedicationEpisode)
        .filter(MedicationEpisode.patient_profile_id == profile.id, MedicationEpisode.status == "active")
        .all()
    )
    observations = (
        db.query(ClinicalObservation)
        .filter(ClinicalObservation.patient_profile_id == profile.id)
        .order_by(desc(ClinicalObservation.observed_at))
        .limit(40)
        .all()
    )

    # Step 1: Deterministic calculations (<50ms)
    latest_by_loinc: Dict[str, float] = {}
    obs_list_for_pdf: List[Dict[str, Any]] = []
    for o in observations:
        if o.loinc_code and o.canonical_value is not None and o.loinc_code not in latest_by_loinc:
            latest_by_loinc[o.loinc_code] = o.canonical_value
        obs_list_for_pdf.append(
            {
                "loinc_code": o.loinc_code,
                "canonical_name": o.raw_name,
                "canonical_value": o.canonical_value if o.canonical_value is not None else o.raw_value,
                "canonical_unit": o.canonical_unit or o.raw_unit or "",
                "reference_range": o.reference_range,
                "flag": o.flag,
                "observed_date": o.observed_at.strftime("%Y-%m-%d") if o.observed_at else "",
            }
        )

    det_scores = compute_deterministic_clinical_scores(
        latest_by_loinc, dob=profile.date_of_birth, sex=profile.sex
    )
    red_flags = evaluate_lab_red_flags(
        [
            {"loinc_code": k, "canonical_value": v}
            for k, v in latest_by_loinc.items()
        ]
    )
    for c in checkins[:3]:
        for rf in (c.red_flags_detected or []):
            red_flags.append(rf)

    med_items_for_ddi = [
        {"brand_name": m.raw_brand_name, "generic_name": m.generic_name, "source": "current_rx"}
        for m in meds
        if m.generic_name
    ]
    ddi_alerts = check_ddi_and_duplicates(med_items_for_ddi, [], db)

    if job_id:
        _update_job(db, job_id, "running", 45, "Running Parallel Clinical Synthesis DAG")

    provider = get_ai_provider()

    checkin_ctx = "\n".join(
        f"[CheckIn #{c.id} | {c.created_at.strftime('%Y-%m-%d')}] Mood={c.mood}; Symptoms={c.symptoms}; Summary={c.summary}"
        for c in checkins
    ) or "None"
    rx_ctx = "\n".join(
        f"[Rx #{p.id} | {p.doc_date or p.created_at.strftime('%Y-%m-%d')}] Doctor={p.doctor_name}; Dx={p.diagnosis}; Summary={p.prescription_summary}"
        for p in prescriptions
    ) or "None"
    lab_ctx = "\n".join(
        f"[Lab #{o['observed_date']}] {o['canonical_name']}: {o['canonical_value']} {o['canonical_unit']} (Flag: {o['flag']})"
        for o in obs_list_for_pdf[:20]
    ) or "None"
    med_ctx = "\n".join(
        f"- {m.raw_brand_name} ({m.generic_name or 'Unverified'}) {m.dosage} {m.frequency_bd}"
        for m in meds
    ) or "None"

    # Step 2: Single consolidated structured synthesis call + deterministic fallback
    unified_prompt = (
        "You are preparing a concise 1-page English Doctor Brief for a Bangladeshi physician's 3-minute consultation.\n"
        "Strictly use ONLY the grounded facts below (never invent lab numbers, diagnostic percentages, or change doses).\n"
        "Tasks:\n"
        "1) Write a crisp 2-sentence patient_snapshot and brief chief_concerns_summary (translating any Bangla/Banglish notes).\n"
        "2) Build up to 5 timeline_events with exact citations like [CheckIn #1] or [Rx #2].\n"
        "3) Summarize normalized lab_trends_narrative and 3-5 factual clinical_observations.\n"
        "4) Write 3-4 practical questions_for_doctor (e.g., clarifying duplicate PPIs or rising HbA1c/creatinine).\n\n"
        f"Patient Conditions: {profile.chronic_conditions}\n"
        f"Deterministic Calculators: {det_scores}\n"
        f"DDI / Duplicate Alerts: {ddi_alerts}\n"
        f"Active Medications:\n{med_ctx}\n"
        f"Normalized Labs:\n{lab_ctx}\n"
        f"Recent Check-Ins:\n{checkin_ctx}\n"
        f"Prescriptions:\n{rx_ctx}"
    )

    synthesis_mode = "llm_grounded"
    try:
        narrative = await provider.generate_structured(unified_prompt, _CombinedBriefNarrative, fast=True)
    except Exception:
        synthesis_mode = "deterministic_fallback"
        narrative = _build_deterministic_fallback_narrative(
            profile=profile,
            checkins=checkins,
            prescriptions=prescriptions,
            obs_list_for_pdf=obs_list_for_pdf,
            det_scores=det_scores,
            ddi_alerts=ddi_alerts,
        )

    if job_id:
        _update_job(db, job_id, "running", 80, "Rendering 1-Page English Clinical Brief PDF + QR token")

    brief_meds: List[BriefMedicationItem] = []
    flagged_brands = {d for a in ddi_alerts for d in a.get("drugs", [])}
    for m in meds:
        flag = "Check DDI / Duplicate" if m.raw_brand_name in flagged_brands else ("Needs Confirm" if m.needs_user_confirm else "Active")
        brief_meds.append(
            BriefMedicationItem(
                brand_name=m.raw_brand_name,
                generic_name=m.generic_name,
                dosage=m.dosage,
                frequency_bd=m.frequency_bd,
                status=m.status,
                flag=flag,
            )
        )

    brief_obj = DoctorBriefOutput(
        patient_snapshot=narrative.patient_snapshot,
        chief_concerns_summary=narrative.chief_concerns_summary,
        timeline_events=narrative.timeline_events,
        lab_trends_narrative=narrative.lab_trends_narrative,
        active_medications=brief_meds,
        clinical_observations=narrative.clinical_observations,
        questions_for_doctor=narrative.questions_for_doctor,
        red_flag_summary=[f"{r.get('title')}: {r.get('action')}" for r in red_flags],
    )

    raw_token = secrets.token_urlsafe(24)
    token_hash = hash_share_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=72)
    share_url = f"{public_base_url.rstrip('/')}/brief/{raw_token}"

    settings = get_settings()
    briefs_dir = os.path.join(settings.upload_dir, str(profile.id), "briefs")
    os.makedirs(briefs_dir, exist_ok=True)
    pdf_rel_path = os.path.join(str(profile.id), "briefs", f"DoctorBrief_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")
    pdf_abs_path = os.path.join(settings.upload_dir, pdf_rel_path)

    age_yrs = compute_age_years(profile.date_of_birth)
    profile_info = {
        "display_name": profile.display_name,
        "age_label": f"{age_yrs}y" if age_yrs else "Age N/A",
        "sex": profile.sex,
        "chronic_conditions": profile.chronic_conditions,
        "allergies": profile.allergies,
    }

    generate_doctor_brief_pdf(
        output_pdf=pdf_abs_path,
        profile_info=profile_info,
        brief_data=brief_obj.model_dump(),
        deterministic_scores=det_scores,
        normalized_labs=obs_list_for_pdf,
        ddi_alerts=ddi_alerts,
        share_url=share_url,
    )

    citations = [t.citation for t in narrative.timeline_events]
    brief_payload = brief_obj.model_dump()
    brief_payload["synthesis_mode"] = synthesis_mode
    brief_payload["ddi_alerts"] = ddi_alerts
    brief_payload["normalized_labs"] = obs_list_for_pdf[:12]
    brief_payload["share_token"] = raw_token
    brief_payload["share_url"] = share_url

    record = DoctorBrief(
        patient_profile_id=profile.id,
        pdf_file_path=pdf_rel_path,
        share_token_hash=token_hash,
        share_expires_at=expires_at,
        brief_payload=brief_payload,
        deterministic_scores=det_scores,
        citations=citations,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    result_payload = {
        "brief_id": record.id,
        "pdf_file_path": record.pdf_file_path,
        "share_token": raw_token,
        "share_url": share_url,
        "share_expires_at": expires_at.isoformat(),
        "brief_payload": brief_payload,
        "deterministic_scores": det_scores,
    }
    if job_id:
        _update_job(db, job_id, "completed", 100, "1-Page Doctor Brief ready", result_id=str(record.id), result_payload=result_payload)
    return result_payload
