import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ai_core.rag.retriever import retrieve_hybrid_context
from ai_core.router import get_ai_provider
from auth.dependencies import get_active_profile
from db.database import get_db
from db.models import PatientProfile

router = APIRouter(prefix="/api/rag", tags=["rag"])


class RagSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=6, ge=1, le=15)
    synthesize_answer: bool = True


@router.post("/search")
async def search_rag(
    req: RagSearchRequest,
    profile: PatientProfile = Depends(get_active_profile),
    db: Session = Depends(get_db),
):
    trace = await retrieve_hybrid_context(db, profile.id, req.query, top_k=req.top_k)

    answer = None
    if req.synthesize_answer and trace.hits:
        provider = get_ai_provider()
        ctx = "\n".join(f"{h.citation}: {h.chunk_text}" for h in trace.hits)
        prompt = (
            "Answer the patient's question strictly from the retrieved clinical context below. "
            "Include inline citations like [Rx #2 | 2026-11-10] or [Lab #3 | 2026-11-14]. "
            "Never invent values or prescribe treatments.\n\n"
            f"Question: {req.query}\n\nRetrieved Context:\n{ctx}"
        )
        try:
            resp = await asyncio.wait_for(
                provider.generate_text(contents=prompt, fast=True),
                timeout=22.0,
            )
            answer = (getattr(resp, "text", None) or "").strip()
        except Exception:
            answer = "Retrieved clinical records:\n" + "\n".join(
                f"- {h.citation}: {h.chunk_text}" for h in trace.hits[:3]
            )

    return {
        "success": True,
        "answer": answer,
        "trace": trace.model_dump(),
    }
