import asyncio
import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from auth.dependencies import get_active_profile
from auth.security import decode_access_token
from db.database import SessionLocal, get_db
from db.models import BackgroundJob, PatientProfile

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}")
def get_job_status(
    job_id: str,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    try:
        jid = uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid job_id")

    job = (
        db.query(BackgroundJob)
        .filter(BackgroundJob.id == jid, BackgroundJob.patient_profile_id == profile.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "job_id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "progress_pct": job.progress_pct,
        "current_step": job.current_step,
        "result_id": job.result_id,
        "result_payload": job.result_payload,
        "error_message": job.error_message,
    }


@router.get("/{job_id}/events")
async def stream_job_events(
    job_id: str,
    token: str = Query(..., description="Bearer JWT passed for EventSource compatibility"),
    profile_id: str = Query(...),
):
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload.get("sub")))
        pid = uuid.UUID(profile_id)
        jid = uuid.UUID(job_id)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token or IDs")

    db = SessionLocal()
    try:
        prof = db.query(PatientProfile).filter(PatientProfile.id == pid, PatientProfile.owner_user_id == user_id).first()
        if not prof:
            raise HTTPException(status_code=403, detail="Access denied")
    finally:
        db.close()

    async def event_gen():
        last_key = None
        for _ in range(400):  # ~120s max
            s = SessionLocal()
            try:
                job = s.query(BackgroundJob).filter(BackgroundJob.id == jid, BackgroundJob.patient_profile_id == pid).first()
                if not job:
                    yield {"event": "error", "data": json.dumps({"detail": "Job not found"})}
                    return
                state_key = (job.status, job.progress_pct, job.current_step)
                if state_key != last_key:
                    last_key = state_key
                    data = {
                        "job_id": str(job.id),
                        "status": job.status,
                        "progress_pct": job.progress_pct,
                        "current_step": job.current_step,
                        "result_id": job.result_id,
                        "result_payload": job.result_payload if job.status == "completed" else None,
                        "error_message": job.error_message,
                    }
                    yield {"event": "progress", "data": json.dumps(data)}
                if job.status in ("completed", "failed"):
                    return
            finally:
                s.close()
            await asyncio.sleep(0.35)

    return EventSourceResponse(event_gen())
