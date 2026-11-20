import asyncio
from datetime import datetime, timezone
from io import BytesIO
import os
from typing import Any, Dict, Optional
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
import qrcode
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.pipelines.brief_dag import run_brief_dag
from auth.dependencies import get_active_profile
from auth.security import hash_share_token, sign_upload_path
from db.database import SessionLocal, get_db
from db.models import BackgroundJob, DoctorBrief, PatientProfile
from utils.pdf_generator import _qr_data_uri

router = APIRouter(prefix="/api", tags=["briefs"])


async def _execute_brief_job(job_id: uuid.UUID, profile_id: uuid.UUID, public_base_url: str):
    db = SessionLocal()
    try:
        await run_brief_dag(db, profile_id, job_id=job_id, public_base_url=public_base_url)
    except Exception as exc:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_step = "Brief generation failed"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()


@router.post("/briefs/generate", status_code=202)
async def generate_brief(
    request: Request,
    background_tasks: BackgroundTasks,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    origin = request.headers.get("origin") or "http://localhost:8080"
    job = BackgroundJob(
        patient_profile_id=profile.id,
        job_type="brief_gen",
        status="queued",
        progress_pct=5,
        current_step="Queued 1-page Doctor Brief synthesis",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(_execute_brief_job, job.id, profile.id, origin)
    return {"job_id": str(job.id), "status": "queued"}


@router.get("/briefs/latest")
def get_latest_brief(
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    brief = (
        db.query(DoctorBrief)
        .filter(DoctorBrief.patient_profile_id == profile.id)
        .order_by(desc(DoctorBrief.created_at))
        .first()
    )
    if not brief:
        raise HTTPException(status_code=404, detail="No doctor brief generated yet for this profile")

    settings = get_settings()
    pdf_exists = bool(brief.pdf_file_path and os.path.exists(os.path.join(settings.upload_dir, brief.pdf_file_path)))
    sig = sign_upload_path(brief.pdf_file_path) if brief.pdf_file_path else ""
    share_url = (brief.brief_payload or {}).get("share_url")
    return {
        "id": brief.id,
        "created_at": brief.created_at.isoformat() if brief.created_at else None,
        "pdf_url": f"/uploads/{brief.pdf_file_path.lstrip('/')}?{sig}" if pdf_exists else None,
        "share_token": (brief.brief_payload or {}).get("share_token"),
        "share_url": share_url,
        "qr_data_uri": _qr_data_uri(share_url) if share_url else None,
        "share_expires_at": brief.share_expires_at.isoformat() if brief.share_expires_at else None,
        "brief_payload": brief.brief_payload,
        "deterministic_scores": brief.deterministic_scores,
        "citations": brief.citations,
    }


@router.get("/briefs/{brief_id}/pdf")
def download_brief_pdf(
    brief_id: int,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    brief = (
        db.query(DoctorBrief)
        .filter(DoctorBrief.id == brief_id, DoctorBrief.patient_profile_id == profile.id)
        .first()
    )
    if not brief or not brief.pdf_file_path:
        raise HTTPException(status_code=404, detail="PDF not found")
    settings = get_settings()
    abs_path = os.path.join(settings.upload_dir, brief.pdf_file_path)
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="PDF file missing on disk")
    return FileResponse(abs_path, media_type="application/pdf", filename=f"MediTrack_DoctorBrief_{brief.id}.pdf")


@router.get("/briefs/{brief_id}/qr.png")
def get_brief_qr(
    brief_id: int,
    request: Request,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    brief = (
        db.query(DoctorBrief)
        .filter(DoctorBrief.id == brief_id, DoctorBrief.patient_profile_id == profile.id)
        .first()
    )
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    share_url = (brief.brief_payload or {}).get("share_url") or str(request.base_url)
    img = qrcode.make(share_url, box_size=6, border=2)
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")


@router.get("/public/brief/{token}")
def get_public_brief(token: str, db: Session = Depends(get_db)):
    """Unauthenticated read-only Doctor Brief endpoint accessed via expiring QR code."""
    token_hash = hash_share_token(token)
    brief = db.query(DoctorBrief).filter(DoctorBrief.share_token_hash == token_hash).first()
    if not brief:
        raise HTTPException(status_code=404, detail="Brief link not found or revoked")
    now = datetime.now(timezone.utc)
    if brief.share_expires_at and brief.share_expires_at < now:
        raise HTTPException(status_code=410, detail="This shared brief link has expired (72h limit)")

    profile = db.query(PatientProfile).filter(PatientProfile.id == brief.patient_profile_id).first()
    return {
        "patient_display_name": profile.display_name if profile else "Patient",
        "sex": profile.sex if profile else None,
        "chronic_conditions": profile.chronic_conditions if profile else [],
        "allergies": profile.allergies if profile else [],
        "generated_at": brief.created_at.isoformat() if brief.created_at else None,
        "expires_at": brief.share_expires_at.isoformat() if brief.share_expires_at else None,
        "brief_payload": brief.brief_payload,
        "deterministic_scores": brief.deterministic_scores,
        "citations": brief.citations,
    }
