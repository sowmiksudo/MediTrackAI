from datetime import datetime, timezone
import os
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.rag.indexer import add_clinical_edge, index_knowledge_chunk
from ai_core.router import get_ai_provider
from ai_core.schemas import RxExtractionResult
from clinical.drug_verifier import verify_medicines
from db.models import BackgroundJob, MedicationEpisode, Prescription


def _guess_mime(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".png":
        return "image/png"
    return "image/jpeg"


def _update_job(db: Session, job_id: Any, status: str, pct: int, step: str, result_id: Optional[str] = None, result_payload: Optional[dict] = None, err: Optional[str] = None):
    job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
    if not job:
        return
    job.status = status
    job.progress_pct = pct
    job.current_step = step
    if result_id is not None:
        job.result_id = str(result_id)
    if result_payload is not None:
        job.result_payload = result_payload
    if err is not None:
        job.error_message = err
    db.commit()


async def run_rx_pipeline(db: Session, prescription_id: int, job_id: Optional[Any] = None) -> Dict[str, Any]:
    rx = db.query(Prescription).filter(Prescription.id == prescription_id).first()
    if not rx:
        raise ValueError("Prescription not found")

    if job_id:
        _update_job(db, job_id, "running", 20, "Reading handwritten prescription with Multimodal VLM")

    provider = get_ai_provider()
    settings = get_settings()
    disk_path = rx.file_path if os.path.isabs(rx.file_path) or os.path.exists(rx.file_path) else os.path.join(settings.upload_dir, rx.file_path)
    with open(disk_path, "rb") as f:
        media_bytes = f.read()
    mime = _guess_mime(disk_path)

    prompt = (
        "You are a Bangladeshi clinical prescription intelligence extractor.\n"
        "Read the attached prescription image/PDF (which may contain doctor handwriting, Bangladeshi brand names like "
        "Napa, Seclo, Sergel, Bizoran, Comet, Osartil, Monas, and Bangla/BD dosage notations like ১+০+১ or 1+0+1).\n"
        "Extract doctor info, BMDC registration if visible, date, diagnosis, symptoms, advice, follow-up, "
        "exact verbatim raw_ocr_text, and EVERY prescribed medicine with dosage and BD frequency.\n"
        "Write a concise English prescription_summary."
    )
    extracted: RxExtractionResult = await provider.generate_structured(
        prompt=prompt,
        response_schema=RxExtractionResult,
        media_bytes=media_bytes,
        mime_type=mime,
        fast=False,
    )

    if job_id:
        _update_job(db, job_id, "running", 60, "Verifying against DGDA Bangladesh Drug Catalog & DDI rules")

    meds_dicts = [m.model_dump() for m in extracted.medicines]
    verification = verify_medicines(meds_dicts, db, patient_profile_id=rx.patient_profile_id)

    rx.doc_date = extracted.prescription_date
    rx.doctor_name = extracted.doctor_name
    rx.doctor_qualification = extracted.doctor_qualification
    rx.doctor_bmdc_reg = extracted.doctor_bmdc_reg
    rx.hospital = extracted.hospital
    rx.diagnosis = extracted.diagnosis
    rx.raw_ocr_text = extracted.raw_ocr_text
    rx.prescription_summary = extracted.prescription_summary
    rx.overall_confidence = verification["overall_confidence"]
    rx.ddi_alerts = verification["ddi_alerts"]
    rx.verification_status = "pending_review" if verification["needs_review"] else "confirmed"
    rx.extracted_json = {
        "doctor_info": {
            "name": extracted.doctor_name,
            "qualification": extracted.doctor_qualification,
            "bmdc_reg": extracted.doctor_bmdc_reg,
            "hospital": extracted.hospital,
            "date": extracted.prescription_date,
        },
        "diagnosis": extracted.diagnosis,
        "symptoms": extracted.symptoms,
        "advice": extracted.advice,
        "follow_up": extracted.follow_up,
        "medicines": verification["medicines"],
        "ddi_alerts": verification["ddi_alerts"],
    }
    db.commit()

    # Persist verified / candidate medication episodes
    db.query(MedicationEpisode).filter(MedicationEpisode.prescription_id == rx.id).delete()
    for item in verification["medicines"]:
        ep = MedicationEpisode(
            patient_profile_id=rx.patient_profile_id,
            prescription_id=rx.id,
            raw_brand_name=item["raw_name"],
            matched_drug_id=item["matched_drug_id"],
            generic_name=item["generic_name"],
            drug_class=item["drug_class"],
            dosage=item["dosage"],
            frequency_bd=item["frequency_bd"],
            special_instructions=item["special_instructions"],
            match_confidence=item["confidence"],
            needs_user_confirm=item["needs_user_confirm"],
            status="active",
        )
        db.add(ep)
    db.commit()

    if job_id:
        _update_job(db, job_id, "running", 85, "Indexing prescription into pgvector Hybrid RAG memory")

    med_lines = ", ".join(
        f"{m['brand_name']} ({m['generic_name'] or 'unverified'}) {m['dosage']} {m['frequency_bd']}"
        for m in verification["medicines"]
    )
    chunk_text = (
        f"Prescription on {rx.doc_date or 'recent date'} by {rx.doctor_name or 'Doctor'} "
        f"({rx.hospital or 'Chamber'}). Diagnosis: {rx.diagnosis or 'N/A'}. "
        f"Medications: {med_lines}. Summary: {rx.prescription_summary}"
    )
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=rx.patient_profile_id,
        source_type="prescription",
        source_id=str(rx.id),
        chunk_text=chunk_text,
        event_at=rx.created_at or datetime.now(timezone.utc),
        language="en",
        metadata={"ddi_count": len(verification["ddi_alerts"])},
        media_bytes=media_bytes,
        media_mime_type=mime,
    )

    for alert in verification["ddi_alerts"]:
        add_clinical_edge(
            db,
            rx.patient_profile_id,
            src_type="prescription",
            src_id=str(rx.id),
            edge_type="TRIGGERED_ALERT",
            dst_type="ddi_rule",
            dst_id=alert["rule_type"],
            metadata=alert,
        )

    payload = {
        "prescription_id": rx.id,
        "verification_status": rx.verification_status,
        "overall_confidence": rx.overall_confidence,
        "medicines": verification["medicines"],
        "ddi_alerts": verification["ddi_alerts"],
        "summary": rx.prescription_summary,
    }
    if job_id:
        _update_job(db, job_id, "completed", 100, "Prescription verified & indexed", result_id=str(rx.id), result_payload=payload)
    return payload
