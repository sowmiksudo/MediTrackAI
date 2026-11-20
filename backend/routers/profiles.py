from datetime import date
from typing import List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from db.database import get_db
from db.models import PatientProfile, PdpaConsent, User

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class ProfileCreate(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=120)
    relationship: str = Field(default="parent", max_length=40)
    date_of_birth: Optional[date] = None
    sex: Optional[str] = Field(default=None, max_length=16)
    chronic_conditions: List[str] = []
    allergies: List[str] = []
    emergency_contact_phone: Optional[str] = None
    accepted_cloud_ai_processing: bool = True


class ProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    relationship: Optional[str] = Field(default=None, max_length=40)
    date_of_birth: Optional[date] = None
    sex: Optional[str] = None
    chronic_conditions: Optional[List[str]] = None
    allergies: Optional[List[str]] = None
    emergency_contact_phone: Optional[str] = None


class ConsentUpdate(BaseModel):
    accepted_local_storage: bool = True
    accepted_cloud_ai_processing: bool = True
    consent_version: str = "bd-pdpa-2026-v1"


def _to_dict(p: PatientProfile, consent: Optional[PdpaConsent] = None) -> dict:
    return {
        "id": str(p.id),
        "display_name": p.display_name,
        "relationship": p.relationship_type,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "sex": p.sex,
        "chronic_conditions": list(p.chronic_conditions or []),
        "allergies": list(p.allergies or []),
        "emergency_contact_phone": p.emergency_contact_phone,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "pdpa_consent": {
            "consent_version": consent.consent_version,
            "accepted_local_storage": consent.accepted_local_storage,
            "accepted_cloud_ai_processing": consent.accepted_cloud_ai_processing,
            "accepted_at": consent.accepted_at.isoformat(),
        }
        if consent
        else None,
    }


def _get_owned_profile(profile_id: str, current_user: User, db: Session) -> PatientProfile:
    try:
        pid = uuid.UUID(profile_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid profile ID")
    profile = db.query(PatientProfile).filter(PatientProfile.id == pid).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    if profile.owner_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return profile


@router.get("")
def list_profiles(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profiles = (
        db.query(PatientProfile)
        .filter(PatientProfile.owner_user_id == current_user.id)
        .order_by(PatientProfile.created_at.asc())
        .all()
    )
    out = []
    for p in profiles:
        latest_consent = (
            db.query(PdpaConsent)
            .filter(PdpaConsent.patient_profile_id == p.id)
            .order_by(PdpaConsent.accepted_at.desc())
            .first()
        )
        out.append(_to_dict(p, latest_consent))
    return {"profiles": out}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(
    req: ProfileCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = PatientProfile(
        owner_user_id=current_user.id,
        display_name=req.display_name.strip(),
        relationship_type=req.relationship,
        date_of_birth=req.date_of_birth,
        sex=req.sex,
        chronic_conditions=req.chronic_conditions,
        allergies=req.allergies,
        emergency_contact_phone=req.emergency_contact_phone,
    )
    db.add(profile)
    db.flush()

    consent = PdpaConsent(
        user_id=current_user.id,
        patient_profile_id=profile.id,
        consent_version="bd-pdpa-2026-v1",
        accepted_local_storage=True,
        accepted_cloud_ai_processing=req.accepted_cloud_ai_processing,
    )
    db.add(consent)
    db.commit()
    db.refresh(profile)
    db.refresh(consent)
    return {"profile": _to_dict(profile, consent)}


@router.put("/{profile_id}")
def update_profile(
    profile_id: str,
    req: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(profile_id, current_user, db)
    data = req.model_dump(exclude_unset=True)
    if "relationship" in data:
        profile.relationship_type = data.pop("relationship")
    for k, v in data.items():
        setattr(profile, k, v)
    db.commit()
    db.refresh(profile)
    return {"profile": _to_dict(profile)}


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(profile_id, current_user, db)
    total = db.query(PatientProfile).filter(PatientProfile.owner_user_id == current_user.id).count()
    if total <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete your only patient profile")
    db.delete(profile)
    db.commit()
    return {"message": "Profile deleted"}


@router.post("/{profile_id}/consent")
def record_consent(
    profile_id: str,
    req: ConsentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(profile_id, current_user, db)
    consent = PdpaConsent(
        user_id=current_user.id,
        patient_profile_id=profile.id,
        consent_version=req.consent_version,
        accepted_local_storage=req.accepted_local_storage,
        accepted_cloud_ai_processing=req.accepted_cloud_ai_processing,
    )
    db.add(consent)
    db.commit()
    db.refresh(consent)
    return {"profile": _to_dict(profile, consent)}


@router.get("/{profile_id}/consent")
def get_consent(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = _get_owned_profile(profile_id, current_user, db)
    consent = (
        db.query(PdpaConsent)
        .filter(PdpaConsent.patient_profile_id == profile.id)
        .order_by(PdpaConsent.accepted_at.desc())
        .first()
    )
    return {"profile_id": str(profile.id), "consent": _to_dict(profile, consent)["pdpa_consent"]}
