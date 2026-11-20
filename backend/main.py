from contextlib import asynccontextmanager
from datetime import datetime, timezone
import os
import pathlib
from typing import Optional
import uuid

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.pipelines.lab_pipeline import run_lab_pipeline
from ai_core.pipelines.rx_pipeline import run_rx_pipeline
from ai_core.rag.indexer import index_knowledge_chunk
from ai_core.router import TELEMETRY_STORE, get_ai_provider
from ai_core.schemas import CheckInSummaryOutput
from auth.dependencies import bearer_scheme, get_active_profile
from auth.security import decode_access_token, verify_upload_signature
from clinical.red_flag_gate import evaluate_text_red_flags
from db.database import SessionLocal, engine, get_db
from db.models import BackgroundJob, CheckIn, PatientProfile, Prescription, Report, User
from routers import auth, briefs, checkins, drugs, jobs, live_ws, prescriptions, profiles, rag, reports, telemetry

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        print(f"Database check warning: {exc}")
    os.makedirs(settings.upload_dir, exist_ok=True)
    yield


app = FastAPI(
    title="MediTrackAI — Bangladesh SOTA Clinical Companion API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _exec_rx_job(job_id: uuid.UUID, rx_id: int):
    db = SessionLocal()
    try:
        await run_rx_pipeline(db, rx_id, job_id=job_id)
    except Exception as exc:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_step = "Prescription extraction failed"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()


async def _exec_lab_job(job_id: uuid.UUID, report_id: int):
    db = SessionLocal()
    try:
        await run_lab_pipeline(db, report_id, job_id=job_id)
    except Exception as exc:
        job = db.query(BackgroundJob).filter(BackgroundJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.current_step = "Lab report extraction failed"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()


@app.get("/uploads/{file_path:path}")
async def serve_upload_file(
    file_path: str,
    sig: Optional[str] = Query(default=None),
    exp: Optional[int] = Query(default=None),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
):
    """Protected PHI file endpoint: requires valid signed URL OR Bearer JWT owning the profile folder."""
    clean_rel = file_path.lstrip("/")
    authorized = False

    if sig and exp is not None:
        authorized = verify_upload_signature(clean_rel, sig, exp)

    if not authorized and credentials and credentials.credentials:
        try:
            payload = decode_access_token(credentials.credentials)
            user_id = uuid.UUID(str(payload.get("sub")))
            first_seg = clean_rel.split("/", 1)[0]
            prof_id = uuid.UUID(first_seg)
            prof = db.query(PatientProfile).filter(PatientProfile.id == prof_id, PatientProfile.owner_user_id == user_id).first()
            if prof:
                authorized = True
        except Exception:
            authorized = False

    if not authorized:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid auth token or signed URL required")

    uploads_base = pathlib.Path(settings.upload_dir).resolve()
    full_path = (uploads_base / clean_rel).resolve()
    try:
        full_path.relative_to(uploads_base)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    media_type = None
    suf = full_path.suffix.lower()
    if suf == ".pdf":
        media_type = "application/pdf"
    elif suf in (".jpg", ".jpeg"):
        media_type = "image/jpeg"
    elif suf == ".png":
        media_type = "image/png"
    elif suf == ".wav":
        media_type = "audio/wav"

    return FileResponse(path=str(full_path), media_type=media_type, filename=full_path.name)


app.include_router(auth.router)
app.include_router(profiles.router)
app.include_router(checkins.router)
app.include_router(prescriptions.router)
app.include_router(reports.router)
app.include_router(briefs.router)
app.include_router(jobs.router)
app.include_router(rag.router)
app.include_router(drugs.router)
app.include_router(telemetry.router)
app.include_router(live_ws.router)


@app.get("/")
def root():
    return {
        "message": "MediTrackAI Bangladesh API",
        "version": "2.0.0",
        "inference_mode": settings.inference_mode,
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "inference_mode": settings.inference_mode}


@app.post("/upload-checkin")
async def upload_checkin(
    file: UploadFile = File(...),
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    safe_name = f"{uuid.uuid4().hex[:8]}_{os.path.basename(file.filename or 'checkin.wav')}"
    rel_path = os.path.join(str(profile.id), "checkins", safe_name)
    abs_path = os.path.join(settings.upload_dir, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    audio_bytes = await file.read()
    with open(abs_path, "wb") as f:
        f.write(audio_bytes)

    provider = get_ai_provider()
    transcript_text, asr_engine = await provider.transcribe_audio_bytes(audio_bytes, is_wav=True)
    pii_res = await provider.redact_pii(transcript_text)
    TELEMETRY_STORE.record_pii(pii_res.model_dump())
    red_flags = evaluate_text_red_flags(transcript_text)

    prompt = (
        "Summarize this bilingual (Bangla/Banglish/English) patient check-in into concise clinical English JSON. "
        "overall_score MUST be one of 'positive', 'neutral', or 'negative'.\n\n"
        f"Redacted Transcript:\n{pii_res.redacted_text}"
    )
    summary_obj = await provider.generate_structured(prompt, CheckInSummaryOutput, fast=True)

    checkin = CheckIn(
        patient_profile_id=profile.id,
        audio_path=rel_path,
        transcript={"engine": asr_engine, "text": transcript_text},
        pii_redacted_transcript={"redacted_text": pii_res.redacted_text, "engine": pii_res.engine},
        summary=summary_obj.summary,
        mood=summary_obj.mood,
        symptoms=summary_obj.symptoms,
        medications_mentioned=summary_obj.medications_taken,
        sleep_quality=summary_obj.sleep_quality,
        energy_level=summary_obj.energy_level,
        concerns=summary_obj.concerns,
        ai_insights=summary_obj.ai_insights,
        red_flags_detected=red_flags,
        overall_score=summary_obj.overall_score,
        language_detected=summary_obj.language_detected,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    await index_knowledge_chunk(
        db=db,
        patient_profile_id=profile.id,
        source_type="checkin",
        source_id=str(checkin.id),
        chunk_text=f"Check-In ({datetime.now(timezone.utc).strftime('%Y-%m-%d')}): {checkin.summary}",
        language=checkin.language_detected or "bn-en",
    )

    return {
        "id": checkin.id,
        "message": "Check-in processed",
        "transcript": transcript_text,
        "summary": summary_obj.model_dump(),
        "red_flags": red_flags,
        "pii_redaction": pii_res.model_dump(),
    }


@app.post("/upload-prescription", status_code=202)
async def upload_prescription(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    safe_name = f"{uuid.uuid4().hex[:8]}_{os.path.basename(file.filename or 'rx.jpg')}"
    rel_path = os.path.join(str(profile.id), "prescriptions", safe_name)
    abs_path = os.path.join(settings.upload_dir, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, "wb") as f:
        f.write(await file.read())

    rx = Prescription(
        patient_profile_id=profile.id,
        file_path=rel_path,
        verification_status="pending_review",
    )
    db.add(rx)
    db.flush()

    job = BackgroundJob(
        patient_profile_id=profile.id,
        job_type="rx_parse",
        status="queued",
        progress_pct=5,
        current_step="Queued handwritten prescription analysis",
        result_id=str(rx.id),
    )
    db.add(job)
    db.commit()
    db.refresh(rx)
    db.refresh(job)

    background_tasks.add_task(_exec_rx_job, job.id, rx.id)
    return {"job_id": str(job.id), "prescription_id": rx.id, "status": "queued"}


@app.post("/upload-lab-report", status_code=202)
async def upload_lab_report(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    safe_name = f"{uuid.uuid4().hex[:8]}_{os.path.basename(file.filename or 'lab.pdf')}"
    rel_path = os.path.join(str(profile.id), "lab_reports", safe_name)
    abs_path = os.path.join(settings.upload_dir, rel_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)

    with open(abs_path, "wb") as f:
        f.write(await file.read())

    rep = Report(
        patient_profile_id=profile.id,
        file_path=rel_path,
        verification_status="confirmed",
    )
    db.add(rep)
    db.flush()

    job = BackgroundJob(
        patient_profile_id=profile.id,
        job_type="lab_parse",
        status="queued",
        progress_pct=5,
        current_step="Queued diagnostic lab extraction & LOINC normalization",
        result_id=str(rep.id),
    )
    db.add(job)
    db.commit()
    db.refresh(rep)
    db.refresh(job)

    background_tasks.add_task(_exec_lab_job, job.id, rep.id)
    return {"job_id": str(job.id), "report_id": rep.id, "status": "queued"}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": "Validation Error", "details": exc.errors()})


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError):
    return JSONResponse(status_code=500, content={"error": "Database Error", "message": "A database error occurred"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)
