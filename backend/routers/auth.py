from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from auth.security import create_access_token, hash_password, verify_password
from db.database import get_db
from db.models import PatientProfile, PdpaConsent, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    phone_e164: Optional[str] = Field(default=None, max_length=32)
    password: str = Field(..., min_length=6, max_length=128)
    accepted_cloud_ai_processing: bool = True


class LoginRequest(BaseModel):
    identifier: str = Field(..., description="Email or phone (+880...)")
    password: str


class ProfileSummary(BaseModel):
    id: str
    display_name: str
    relationship: str
    sex: Optional[str] = None
    date_of_birth: Optional[str] = None
    chronic_conditions: List[str] = []
    allergies: List[str] = []


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict
    profiles: List[ProfileSummary]


def _serialize_profile(p: PatientProfile) -> ProfileSummary:
    return ProfileSummary(
        id=str(p.id),
        display_name=p.display_name,
        relationship=p.relationship_type,
        sex=p.sex,
        date_of_birth=p.date_of_birth.isoformat() if p.date_of_birth else None,
        chronic_conditions=list(p.chronic_conditions or []),
        allergies=list(p.allergies or []),
    )


def _build_auth_response(user: User, db: Session) -> AuthResponse:
    profiles = (
        db.query(PatientProfile)
        .filter(PatientProfile.owner_user_id == user.id)
        .order_by(PatientProfile.created_at.asc())
        .all()
    )
    token = create_access_token(str(user.id), email=user.email)
    return AuthResponse(
        access_token=token,
        user={
            "id": str(user.id),
            "full_name": user.full_name,
            "email": user.email,
            "phone_e164": user.phone_e164,
            "role": getattr(user, "role", "user") or "user",
        },
        profiles=[_serialize_profile(p) for p in profiles],
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower() if req.email else None
    phone_clean = req.phone_e164.strip() if req.phone_e164 else None
    if not email_clean and not phone_clean:
        raise HTTPException(status_code=400, detail="Provide either email or phone number (+880...)")

    if email_clean and db.query(User).filter(User.email == email_clean).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if phone_clean and db.query(User).filter(User.phone_e164 == phone_clean).first():
        raise HTTPException(status_code=409, detail="Phone number already registered")

    user = User(
        email=email_clean,
        phone_e164=phone_clean,
        password_hash=hash_password(req.password),
        full_name=req.full_name.strip(),
    )
    db.add(user)
    db.flush()

    default_profile = PatientProfile(
        owner_user_id=user.id,
        display_name=req.full_name.strip(),
        relationship_type="self",
        chronic_conditions=[],
        allergies=[],
    )
    db.add(default_profile)
    db.flush()

    consent = PdpaConsent(
        user_id=user.id,
        patient_profile_id=default_profile.id,
        consent_version="bd-pdpa-2026-v1",
        accepted_local_storage=True,
        accepted_cloud_ai_processing=req.accepted_cloud_ai_processing,
    )
    db.add(consent)
    db.commit()
    db.refresh(user)
    return _build_auth_response(user, db)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    ident = req.identifier.strip()
    ident_lower = ident.lower()
    user = db.query(User).filter((User.email == ident_lower) | (User.phone_e164 == ident)).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return _build_auth_response(user, db)


@router.post("/demo-login", response_model=AuthResponse)
def demo_login(db: Session = Depends(get_db)):
    """1-click login into the pre-seeded Dhaka Family Caregiver demo account."""
    user = db.query(User).filter(User.email == "demo@meditrack.bd").first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="Demo account not seeded yet. Run: python -m seeds.seed_demo",
        )
    return _build_auth_response(user, db)


@router.get("/me")
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profiles = (
        db.query(PatientProfile)
        .filter(PatientProfile.owner_user_id == current_user.id)
        .order_by(PatientProfile.created_at.asc())
        .all()
    )
    return {
        "user": {
            "id": str(current_user.id),
            "full_name": current_user.full_name,
            "email": current_user.email,
            "phone_e164": current_user.phone_e164,
            "role": getattr(current_user, "role", "user") or "user",
        },
        "profiles": [_serialize_profile(p).model_dump() for p in profiles],
    }
