from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ai_core.rag.indexer import index_knowledge_chunk
from auth.dependencies import get_active_profile
from auth.security import sign_upload_path
from clinical.drug_verifier import verify_medicines
from db.database import get_db
from db.models import MedicationEpisode, PatientProfile, Prescription

router = APIRouter(prefix="/api/prescriptions", tags=["prescriptions"])


class ConfirmMedicineItem(BaseModel):
    name: str
    dosage: Optional[str] = ""
    frequency: Optional[str] = ""
    duration: Optional[str] = ""
    special_instructions: Optional[str] = ""


class ConfirmPrescriptionRequest(BaseModel):
    medicines: List[ConfirmMedicineItem]
    diagnosis: Optional[str] = None


@router.get("/summaries")
def get_prescription_summaries(
    limit: int = Query(default=20, ge=1, le=100),
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Prescription)
        .filter(Prescription.patient_profile_id == profile.id)
        .order_by(desc(Prescription.created_at))
        .limit(limit)
        .all()
    )
    items = []
    for p in rows:
        ext = p.extracted_json or {}
        eps = (
            db.query(MedicationEpisode)
            .filter(MedicationEpisode.prescription_id == p.id)
            .all()
        )
        meds_out = [
            {
                "id": ep.id,
                "brand_name": ep.raw_brand_name,
                "generic_name": ep.generic_name,
                "drug_class": ep.drug_class,
                "dosage": ep.dosage,
                "frequency_bd": ep.frequency_bd,
                "special_instructions": ep.special_instructions,
                "confidence": ep.match_confidence,
                "needs_user_confirm": ep.needs_user_confirm,
                "status": ep.status,
            }
            for ep in eps
        ] or ext.get("medicines", [])

        sig = sign_upload_path(p.file_path)
        items.append(
            {
                "id": p.id,
                "timestamp": p.created_at.isoformat() if p.created_at else None,
                "prescription_date": p.doc_date or "",
                "doctor_name": p.doctor_name or "",
                "doctor_qualification": p.doctor_qualification or "",
                "doctor_bmdc_reg": p.doctor_bmdc_reg or "",
                "hospital": p.hospital or "",
                "diagnosis": p.diagnosis or "",
                "symptoms": ext.get("symptoms") or "",
                "advice": ext.get("advice") or "",
                "follow_up": ext.get("follow_up") or "",
                "prescription_summary": p.prescription_summary or "",
                "verification_status": p.verification_status,
                "overall_confidence": p.overall_confidence,
                "ddi_alerts": p.ddi_alerts or [],
                "medicines": meds_out,
                "file_url": f"/uploads/{p.file_path.lstrip('/')}?{sig}",
            }
        )
    return {"success": True, "count": len(items), "prescriptions": items}


@router.get("/medications/active")
def get_active_medications(
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    eps = (
        db.query(MedicationEpisode)
        .filter(MedicationEpisode.patient_profile_id == profile.id)
        .order_by(desc(MedicationEpisode.started_at))
        .all()
    )
    return {
        "medications": [
            {
                "id": e.id,
                "prescription_id": e.prescription_id,
                "brand_name": e.raw_brand_name,
                "generic_name": e.generic_name,
                "drug_class": e.drug_class,
                "dosage": e.dosage,
                "frequency_bd": e.frequency_bd,
                "confidence": e.match_confidence,
                "needs_user_confirm": e.needs_user_confirm,
                "status": e.status,
                "started_at": e.started_at.isoformat() if e.started_at else None,
            }
            for e in eps
        ]
    }


@router.get("/{prescription_id}")
def get_prescription(
    prescription_id: int,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    p = (
        db.query(Prescription)
        .filter(Prescription.id == prescription_id, Prescription.patient_profile_id == profile.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Prescription not found")
    sig = sign_upload_path(p.file_path)
    return {
        "id": p.id,
        "timestamp": p.created_at.isoformat() if p.created_at else None,
        "doc_date": p.doc_date,
        "doctor_name": p.doctor_name,
        "hospital": p.hospital,
        "diagnosis": p.diagnosis,
        "raw_ocr_text": p.raw_ocr_text,
        "prescription_summary": p.prescription_summary,
        "verification_status": p.verification_status,
        "overall_confidence": p.overall_confidence,
        "ddi_alerts": p.ddi_alerts or [],
        "extracted_json": p.extracted_json or {},
        "file_url": f"/uploads/{p.file_path.lstrip('/')}?{sig}",
    }


@router.post("/{prescription_id}/confirm")
async def confirm_prescription(
    prescription_id: int,
    req: ConfirmPrescriptionRequest,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    p = (
        db.query(Prescription)
        .filter(Prescription.id == prescription_id, Prescription.patient_profile_id == profile.id)
        .first()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Prescription not found")

    # Remove old episodes for this Rx before re-verifying against other active meds
    db.query(MedicationEpisode).filter(MedicationEpisode.prescription_id == p.id).delete()
    db.commit()

    verification = verify_medicines([m.model_dump() for m in req.medicines], db, patient_profile_id=profile.id)

    for item in verification["medicines"]:
        db.add(
            MedicationEpisode(
                patient_profile_id=profile.id,
                prescription_id=p.id,
                raw_brand_name=item["raw_name"],
                matched_drug_id=item["matched_drug_id"],
                generic_name=item["generic_name"],
                drug_class=item["drug_class"],
                dosage=item["dosage"],
                frequency_bd=item["frequency_bd"],
                special_instructions=item["special_instructions"],
                match_confidence=item["confidence"],
                needs_user_confirm=False,
                status="active",
            )
        )

    if req.diagnosis is not None:
        p.diagnosis = req.diagnosis
    p.verification_status = "confirmed"
    p.overall_confidence = verification["overall_confidence"]
    p.ddi_alerts = verification["ddi_alerts"]
    ext = dict(p.extracted_json or {})
    ext["medicines"] = verification["medicines"]
    ext["ddi_alerts"] = verification["ddi_alerts"]
    p.extracted_json = ext
    db.commit()

    med_lines = ", ".join(
        f"{m['brand_name']} ({m['generic_name'] or 'custom'}) {m['dosage']} {m['frequency_bd']}"
        for m in verification["medicines"]
    )
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=profile.id,
        source_type="prescription",
        source_id=str(p.id),
        chunk_text=f"Confirmed Prescription ({p.doc_date or 'N/A'}) by {p.doctor_name or 'Doctor'}: {med_lines}. Diagnosis: {p.diagnosis or 'N/A'}.",
        event_at=p.created_at or datetime.now(timezone.utc),
        language="en",
    )

    return {
        "success": True,
        "prescription_id": p.id,
        "verification_status": p.verification_status,
        "medicines": verification["medicines"],
        "ddi_alerts": verification["ddi_alerts"],
    }
