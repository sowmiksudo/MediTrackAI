from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from ai_core.router import get_ai_provider
from db.models import ClinicalEdge, KnowledgeChunk


async def index_knowledge_chunk(
    db: Session,
    patient_profile_id: Any,
    source_type: str,
    source_id: str,
    chunk_text: str,
    event_at: Optional[datetime] = None,
    language: str = "en",
    metadata: Optional[Dict[str, Any]] = None,
    media_bytes: Optional[bytes] = None,
    media_mime_type: Optional[str] = None,
) -> KnowledgeChunk:
    provider = get_ai_provider()
    vec_text, sparse_weights, embed_label = await provider.embed_text(chunk_text)

    # Optionally compute multimodal media embedding in Cloud / Gemini space
    mm_vec = None
    if media_bytes and media_mime_type:
        mm_vec = await provider.embed_media(media_bytes, media_mime_type, caption=chunk_text[:1000])

    col_bge = vec_text if len(vec_text) == 1024 else None
    col_gem = vec_text if len(vec_text) == 1536 else mm_vec

    # Upsert by (patient_profile_id, source_type, source_id)
    existing = (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.patient_profile_id == patient_profile_id,
            KnowledgeChunk.source_type == source_type,
            KnowledgeChunk.source_id == str(source_id),
        )
        .first()
    )
    meta = dict(metadata or {})
    meta["embed_backend"] = embed_label

    if existing:
        existing.chunk_text = chunk_text
        existing.language = language
        existing.event_at = event_at or datetime.now(timezone.utc)
        existing.chunk_metadata = meta
        if col_bge is not None:
            existing.embedding_bge_m3 = col_bge
        if col_gem is not None:
            existing.embedding_gemini_mm = col_gem
        if sparse_weights is not None:
            existing.bge_sparse_weights = sparse_weights
        db.commit()
        db.refresh(existing)
        return existing

    chunk = KnowledgeChunk(
        patient_profile_id=patient_profile_id,
        source_type=source_type,
        source_id=str(source_id),
        chunk_text=chunk_text,
        language=language,
        event_at=event_at or datetime.now(timezone.utc),
        chunk_metadata=meta,
        embedding_bge_m3=col_bge,
        embedding_gemini_mm=col_gem,
        bge_sparse_weights=sparse_weights,
    )
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return chunk


def add_clinical_edge(
    db: Session,
    patient_profile_id: Any,
    src_type: str,
    src_id: str,
    edge_type: str,
    dst_type: str,
    dst_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> ClinicalEdge:
    edge = ClinicalEdge(
        patient_profile_id=patient_profile_id,
        src_type=src_type,
        src_id=str(src_id),
        edge_type=edge_type,
        dst_type=dst_type,
        dst_id=str(dst_id),
        edge_metadata=metadata or {},
    )
    db.add(edge)
    db.commit()
    return edge
