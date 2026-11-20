from typing import Optional
import uuid

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from auth.security import decode_access_token
from db.database import get_db
from db.models import PatientProfile, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(str(payload.get("sub")))
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_active_profile(
    x_profile_id: Optional[str] = Header(default=None, alias="X-Profile-Id"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientProfile:
    if x_profile_id:
        try:
            profile_uuid = uuid.UUID(x_profile_id.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid X-Profile-Id header")

        profile = db.query(PatientProfile).filter(PatientProfile.id == profile_uuid).first()
        if not profile:
            raise HTTPException(status_code=404, detail="Patient profile not found")
        if profile.owner_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied to requested patient profile")
        return profile

    profile = (
        db.query(PatientProfile)
        .filter(PatientProfile.owner_user_id == current_user.id)
        .order_by(PatientProfile.created_at.asc())
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="No patient profile found for account")
    return profile


def resolve_ws_user_and_profile(
    token: Optional[str],
    profile_id: Optional[str],
    db: Session,
) -> tuple[User, PatientProfile]:
    """Authenticate WebSocket connection via query parameters."""
    if not token:
        raise PermissionError("Missing auth token")
    try:
        payload = decode_access_token(token)
        user_id = uuid.UUID(str(payload.get("sub")))
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise PermissionError("Invalid or expired token") from exc

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise PermissionError("User not found")

    if profile_id:
        try:
            pid = uuid.UUID(profile_id)
        except ValueError as exc:
            raise PermissionError("Invalid profile_id") from exc
        profile = db.query(PatientProfile).filter(PatientProfile.id == pid).first()
        if not profile or profile.owner_user_id != user.id:
            raise PermissionError("Profile access denied")
        return user, profile

    profile = (
        db.query(PatientProfile)
        .filter(PatientProfile.owner_user_id == user.id)
        .order_by(PatientProfile.created_at.asc())
        .first()
    )
    if not profile:
        raise PermissionError("No patient profile found")
    return user, profile
