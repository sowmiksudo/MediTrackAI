from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from clinical.drug_verifier import lookup_bd_drug
from db.database import get_db
from db.models import User

router = APIRouter(prefix="/api/drugs", tags=["drugs"])


@router.get("/search")
def search_bd_drugs(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=8, ge=1, le=20),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    matches = lookup_bd_drug(q, db, limit=limit)
    return {"query": q, "results": matches}
