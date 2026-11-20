from collections import defaultdict
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from auth.dependencies import get_active_profile
from auth.security import sign_upload_path
from clinical.risk_calculators import compute_deterministic_clinical_scores
from db.database import get_db
from db.models import ClinicalObservation, PatientProfile, Report

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/summaries")
def get_report_summaries(
    limit: int = Query(default=20, ge=1, le=100),
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    reports = (
        db.query(Report)
        .filter(Report.patient_profile_id == profile.id)
        .order_by(desc(Report.created_at))
        .limit(limit)
        .all()
    )
    items = []
    for r in reports:
        obs = (
            db.query(ClinicalObservation)
            .filter(ClinicalObservation.source_type == "lab", ClinicalObservation.source_id == r.id)
            .all()
        )
        metrics_out = [
            {
                "loinc_code": o.loinc_code,
                "test_name": o.raw_name,
                "value": o.canonical_value if o.canonical_value is not None else o.raw_value,
                "unit": o.canonical_unit or o.raw_unit or "",
                "raw_value": o.raw_value,
                "raw_unit": o.raw_unit or "",
                "reference_range": o.reference_range or "",
                "flag": o.flag,
            }
            for o in obs
        ]
        sig = sign_upload_path(r.file_path)
        items.append(
            {
                "id": r.id,
                "timestamp": r.created_at.isoformat() if r.created_at else None,
                "lab_name": r.lab_name or "",
                "report_date": r.report_date or "",
                "lab_summary_overview": r.lab_summary_overview or "",
                "critical_alerts": r.critical_alerts or [],
                "deterministic_scores": r.deterministic_scores or {},
                "metrics": metrics_out,
                "file_url": f"/uploads/{r.file_path.lstrip('/')}?{sig}",
            }
        )
    return {"success": True, "count": len(items), "reports": items}


@router.get("/trends")
def get_lab_trends(
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    obs = (
        db.query(ClinicalObservation)
        .filter(ClinicalObservation.patient_profile_id == profile.id)
        .order_by(asc(ClinicalObservation.observed_at))
        .all()
    )
    series: Dict[str, Dict[str, Any]] = {}
    latest_by_loinc: Dict[str, float] = {}

    for o in obs:
        key = o.loinc_code or o.raw_name
        if key not in series:
            series[key] = {
                "loinc_code": o.loinc_code,
                "metric_name": o.raw_name,
                "unit": o.canonical_unit or o.raw_unit or "",
                "points": [],
            }
        if o.canonical_value is not None:
            series[key]["points"].append(
                {
                    "date": o.observed_at.strftime("%Y-%m-%d") if o.observed_at else "",
                    "value": o.canonical_value,
                    "flag": o.flag,
                    "raw": f"{o.raw_value} {o.raw_unit or ''}".strip(),
                }
            )
            if o.loinc_code:
                latest_by_loinc[o.loinc_code] = o.canonical_value

    det_scores = compute_deterministic_clinical_scores(latest_by_loinc, profile.date_of_birth, profile.sex)
    return {
        "success": True,
        "trends": [v for v in series.values() if v["points"]],
        "deterministic_scores": det_scores,
    }


@router.get("/{report_id}")
def get_report(
    report_id: int,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    r = (
        db.query(Report)
        .filter(Report.id == report_id, Report.patient_profile_id == profile.id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Report not found")
    sig = sign_upload_path(r.file_path)
    return {
        "id": r.id,
        "timestamp": r.created_at.isoformat() if r.created_at else None,
        "lab_name": r.lab_name,
        "report_date": r.report_date,
        "raw_ocr_text": r.raw_ocr_text,
        "lab_summary_overview": r.lab_summary_overview,
        "critical_alerts": r.critical_alerts or [],
        "deterministic_scores": r.deterministic_scores or {},
        "extracted_json": r.extracted_json or {},
        "file_url": f"/uploads/{r.file_path.lstrip('/')}?{sig}",
    }
