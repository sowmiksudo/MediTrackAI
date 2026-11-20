from fastapi import APIRouter, Depends

from ai_core.router import TELEMETRY_STORE, get_ai_provider
from auth.dependencies import get_current_user
from db.models import User

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])


@router.get("/status")
def telemetry_status(_user: User = Depends(get_current_user)):
    provider = get_ai_provider()
    return {
        "runtime": provider.get_telemetry(),
        "traces": TELEMETRY_STORE.snapshot(),
    }
