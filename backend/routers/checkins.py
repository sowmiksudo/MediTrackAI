from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ai_core.rag.indexer import index_knowledge_chunk
from ai_core.router import TELEMETRY_STORE, get_ai_provider
from ai_core.schemas import CheckInSummaryOutput
from auth.dependencies import get_active_profile
from clinical.red_flag_gate import evaluate_text_red_flags
from db.database import get_db
from db.models import CheckIn, PatientProfile

router = APIRouter(prefix="/checkins", tags=["checkins"])


class TurnItem(BaseModel):
    role: str
    text: str


class FinalizeCheckInRequest(BaseModel):
    turns: List[TurnItem]


@router.post("/finalize")
async def finalize_checkin(
    req: FinalizeCheckInRequest,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    if not req.turns:
        raise HTTPException(status_code=400, detail="No conversation turns provided")

    raw_text = "\n".join(f"{t.role}: {t.text}" for t in req.turns)
    provider = get_ai_provider()
    pii_res = await provider.redact_pii(raw_text)
    TELEMETRY_STORE.record_pii(pii_res.model_dump())
    red_flags = evaluate_text_red_flags(raw_text)

    prompt = (
        "Summarize this bilingual (Bangla/Banglish/English) patient health check-in into concise clinical English JSON.\n"
        "Extract summary, mood, symptoms, medications_taken, sleep_quality, energy_level, concerns, "
        "non-diagnostic ai_insights (self-care or questions for doctor), language_detected, and overall_score "
        "which MUST be one of: 'positive', 'neutral', or 'negative'.\n\n"
        f"Redacted Conversation:\n{pii_res.redacted_text}"
    )
    summary_obj = await provider.generate_structured(prompt, CheckInSummaryOutput, fast=True)

    checkin = CheckIn(
        patient_profile_id=profile.id,
        transcript={"turns": [t.model_dump() for t in req.turns]},
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

    chunk_text = (
        f"Check-In ({checkin.created_at.strftime('%Y-%m-%d')}): {checkin.summary} "
        f"Symptoms: {', '.join(checkin.symptoms or [])}. Medications mentioned: {', '.join(checkin.medications_mentioned or [])}."
    )
    await index_knowledge_chunk(
        db=db,
        patient_profile_id=profile.id,
        source_type="checkin",
        source_id=str(checkin.id),
        chunk_text=chunk_text,
        event_at=checkin.created_at or datetime.now(timezone.utc),
        language=checkin.language_detected or "bn-en",
    )

    return {
        "success": True,
        "id": checkin.id,
        "summary": summary_obj.model_dump(),
        "red_flags": red_flags,
        "pii_redaction": pii_res.model_dump(),
    }


@router.get("/summaries")
def get_checkin_summaries(
    limit: int = Query(default=20, ge=1, le=100),
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    checkins = (
        db.query(CheckIn)
        .filter(CheckIn.patient_profile_id == profile.id)
        .order_by(desc(CheckIn.created_at))
        .limit(limit)
        .all()
    )
    return {
        "success": True,
        "count": len(checkins),
        "checkins": [
            {
                "id": c.id,
                "timestamp": c.created_at.isoformat() if c.created_at else None,
                "summary": c.summary or "",
                "mood": c.mood or "Neutral",
                "symptoms": c.symptoms or [],
                "medications_taken": c.medications_mentioned or [],
                "sleep_quality": c.sleep_quality or "",
                "energy_level": c.energy_level or "",
                "concerns": c.concerns or [],
                "ai_insights": c.ai_insights or [],
                "red_flags_detected": c.red_flags_detected or [],
                "overall_score": c.overall_score or "neutral",
                "language_detected": c.language_detected or "bn-en",
            }
            for c in checkins
        ],
    }


@router.get("/{checkin_id}")
def get_checkin_detail(
    checkin_id: int,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    c = (
        db.query(CheckIn)
        .filter(CheckIn.id == checkin_id, CheckIn.patient_profile_id == profile.id)
        .first()
    )
    if not c:
        raise HTTPException(status_code=404, detail="Check-in not found")
    return {
        "id": c.id,
        "timestamp": c.created_at.isoformat() if c.created_at else None,
        "transcript": c.transcript or {},
        "pii_redacted_transcript": c.pii_redacted_transcript or {},
        "summary": c.summary or "",
        "mood": c.mood or "",
        "symptoms": c.symptoms or [],
        "medications_taken": c.medications_mentioned or [],
        "sleep_quality": c.sleep_quality or "",
        "energy_level": c.energy_level or "",
        "concerns": c.concerns or [],
        "ai_insights": c.ai_insights or [],
        "red_flags_detected": c.red_flags_detected or [],
        "overall_score": c.overall_score or "neutral",
    }
