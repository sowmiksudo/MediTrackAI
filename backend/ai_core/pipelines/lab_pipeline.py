from datetime import datetime, timezone
import os
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.pipelines.rx_pipeline import _guess_mime, _update_job
from ai_core.rag.indexer import add_clinical_edge, index_knowledge_chunk
from ai_core.router import get_ai_provider
from ai_core.schemas import LabExtractionResult
from clinical.red_flag_gate import evaluate_lab_red_flags
from clinical.risk_calculators import compute_deterministic_clinical_scores
from clinical.unit_normalizer import normalize_lab_metrics
from db.models import ClinicalObservation, PatientProfile, Report


async def run_lab_pipeline(db: Session, report_id: int, job_id: Optional[Any] = None) -> Dict[str, Any]:
    report = db.query(Report).filter(Report.id == report_id).first()
    if not report:
        raise ValueError("Lab report not found")
    profile = db.query(PatientProfile).filter(PatientProfile.id == report.patient_profile_id).first()

    if job_id:
        _update_job(db, job_id, "running", 25, "Extracting lab panels with Multimodal VLM")

    provider = get_ai_provider()
    settings = get_settings()
    disk_path = report.file_path if os.path.isabs(report.file_path) or os.path.exists(report.file_path) else os.path.join(settings.upload_dir, report.file_path)
    with open(disk_path, "rb") as f:
        media_bytes = f.read()
    mime = _guess_mime(disk_path)

    prompt = (
        "Extract structured diagnostic laboratory report values from the attached image/PDF. "
        "Capture the diagnostic lab name, report_date (ISO YYYY-MM-DD if determinable), raw_ocr_text, "
        "every numeric test metric (test_name, value, unit such as mmol/L, mg/dL, %, /uL, U/L, and reference_range), "
        "and a concise factual English lab_summary_overview without making medical diagnoses."
    )
    extracted: LabExtractionResult = await provider.generate_structured(
        prompt=prompt,
        response_schema=LabExtractionResult,
        media_bytes=media_bytes,
        mime_type=mime,
        fast=False,
    )

    if job_id:
        _update_job(db, job_id, "running", 60, "Normalizing LOINC units (mmol/L <-> mg/dL) & running clinical gates")

    normalized = normalize_lab_metrics([m.model_dump() for m in extracted.metrics], db, sex=profile.sex if profile else None)

    obs_dt = datetime.now(timezone.utc)
    if extracted.report_date:
        try:
            obs_dt = datetime.fromisoformat(extracted.report_date).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    db.query(ClinicalObservation).filter(
        ClinicalObservation.source_type == "lab",
        ClinicalObservation.source_id == report.id,
    ).delete()

    obs_dicts = []
    latest_by_loinc: Dict[str, float] = {}
    for item in normalized:
        co = ClinicalObservation(
            patient_profile_id=report.patient_profile_id,
            source_type="lab",
            source_id=report.id,
            loinc_code=item.loinc_code,
            raw_name=item.raw_name,
            raw_value=item.raw_value,
            raw_unit=item.raw_unit,
            canonical_value=item.canonical_value,
            canonical_unit=item.canonical_unit,
            reference_range=item.reference_range,
            flag=item.flag,
            observed_at=obs_dt,
        )
        db.add(co)
        obs_dicts.append(
            {
                "loinc_code": item.loinc_code,
                "canonical_name": item.canonical_name,
                "canonical_value": item.canonical_value,
                "canonical_unit": item.canonical_unit,
                "reference_range": item.reference_range,
                "flag": item.flag,
            }
        )
        if item.loinc_code and item.canonical_value is not None:
            latest_by_loinc[item.loinc_code] = item.canonical_value

    # Merge any historic latest LOINC values if needed for CKD-EPI / Glycemic calculator
    det_scores = compute_deterministic_clinical_scores(
        latest_by_loinc,
        dob=profile.date_of_birth if profile else None,
        sex=profile.sex if profile else None,
    )
    if det_scores["egfr_ckd_epi"].get("status") == "computed":
        egfr_val = det_scores["egfr_ckd_epi"]["egfr_ml_min"]
        obs_dicts.append({"loinc_code": "98979-8", "canonical_name": "eGFR (CKD-EPI 2021)", "canonical_value": egfr_val, "canonical_unit": "mL/min/1.73m2", "flag": "low" if egfr_val < 60 else "normal"})

    red_flags = evaluate_lab_red_flags(obs_dicts)

    report.lab_name = extracted.lab_name
    report.report_date = extracted.report_date
    report.raw_ocr_text = extracted.raw_ocr_text
    report.lab_summary_overview = extracted.lab_summary_overview
    report.critical_alerts = red_flags
    report.deterministic_scores = det_scores
    report.extracted_json = {
        "lab_name": extracted.lab_name,
        "report_date": extracted.report_date,
        "normalized_metrics": obs_dicts,
    }
    db.commit()

    if job_id:
        _update_job(db, job_id, "running", 85, "Indexing normalized labs into pgvector Hybrid RAG")

    metric_summary = "; ".join(
        f"{o['canonical_name']}: {o['canonical_value']} {o['canonical_unit'] or ''} ({o['flag'].upper()})"
        for o in obs_dicts
    )
    chunk_text = (
        f"Lab Report ({report.lab_name or 'Diagnostic Lab'}) on {report.report_date or obs_dt.strftime('%Y-%m-%d')}: "
        f"{metric_summary}. Overview: {report.lab_summary_overview}"
    )
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=report.patient_profile_id,
        source_type="lab_report",
        source_id=str(report.id),
        chunk_text=chunk_text,
        event_at=obs_dt,
        language="en",
        metadata={"critical_count": len(red_flags)},
        media_bytes=media_bytes,
        media_mime_type=mime,
    )

    for rf in red_flags:
        add_clinical_edge(
            db,
            report.patient_profile_id,
            src_type="lab_report",
            src_id=str(report.id),
            edge_type="TRIGGERED_ALERT",
            dst_type="red_flag",
            dst_id=rf["code"],
            metadata=rf,
        )

    payload = {
        "report_id": report.id,
        "lab_name": report.lab_name,
        "report_date": report.report_date,
        "normalized_metrics": obs_dicts,
        "deterministic_scores": det_scores,
        "critical_alerts": red_flags,
        "overview": report.lab_summary_overview,
    }
    if job_id:
        _update_job(db, job_id, "completed", 100, "Lab normalized & indexed", result_id=str(report.id), result_payload=payload)
    return payload
