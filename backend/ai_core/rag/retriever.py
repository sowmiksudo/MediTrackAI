from datetime import datetime, timezone
import math
import time
from typing import Any, Dict, List
from sqlalchemy import text
from sqlalchemy.orm import Session

from ai_core.config import get_settings
from ai_core.router import TELEMETRY_STORE, get_ai_provider
from ai_core.schemas import RetrievalHit, RetrievalTrace

_BANGLISH_GLOSSARY = {
    "sugar": "glucose fasting blood sugar hba1c diabetes comet metformin",
    "সুগার": "glucose fasting blood sugar hba1c diabetes comet metformin",
    "ডায়াবেটিস": "diabetes glucose hba1c metformin gliclazide",
    "diabetes": "glucose hba1c fasting blood sugar comet metformin",
    "pressure": "blood pressure hypertension bizoran amlodipine losartan osartil",
    "প্রেসার": "blood pressure hypertension bizoran amlodipine losartan",
    "gas": "gastric acidity ppi omeprazole esomeprazole seclo sergel maxpro",
    "গ্যাস": "gastric acidity ppi omeprazole esomeprazole seclo sergel",
    "oshudh": "medication medicine prescription tablet capsule",
    "osudh": "medication medicine prescription tablet capsule",
    "ওষুধ": "medication medicine prescription tablet capsule",
    "kidney": "creatinine egfr renal kidney function",
    "কিডনি": "creatinine egfr renal kidney function",
    "dengue": "platelets cbc hematocrit fever napa dengue",
    "ডেঙ্গু": "platelets cbc hematocrit fever napa dengue",
    "fever": "temperature paracetamol napa ace cbc platelets",
    "জ্বর": "temperature paracetamol napa ace cbc platelets",
    "cholesterol": "lipid ldl hdl triglycerides rosuva atorva",
    "thyroid": "tsh levothyroxine thyrox thyronorm",
    "report": "lab test observation metric value",
    "রিপোর্ট": "lab test observation metric value",
}


def expand_banglish_query(query: str) -> str:
    q_lower = query.lower()
    extras: List[str] = []
    for k, expansion in _BANGLISH_GLOSSARY.items():
        if k in q_lower:
            extras.append(expansion)
    if not extras:
        return query
    return f"{query} {' '.join(extras)}"


def _citation_for(source_type: str, source_id: str, event_at: datetime) -> str:
    tag_map = {
        "prescription": "Rx",
        "lab_report": "Lab",
        "checkin": "CheckIn",
        "medication": "Med",
        "observation": "Obs",
    }
    tag = tag_map.get(source_type, source_type.title())
    d_str = event_at.strftime("%Y-%m-%d") if event_at else "N/A"
    return f"[{tag} #{source_id} | {d_str}]"


async def retrieve_hybrid_context(
    db: Session,
    patient_profile_id: Any,
    query: str,
    top_k: int = 6,
) -> RetrievalTrace:
    t0 = time.perf_counter()
    settings = get_settings()
    provider = get_ai_provider()
    expanded_query = expand_banglish_query(query)

    q_vec, _sparse, embed_label = await provider.embed_text(expanded_query)
    pid_str = str(patient_profile_id)
    vec_col = "embedding_bge_m3" if len(q_vec) == 1024 else "embedding_gemini_mm"
    vec_literal = "[" + ",".join(f"{v:.6f}" for v in q_vec) + "]"

    # 1) pgvector ANN Cosine similarity
    vec_sql = text(
        f"""
        SELECT id::text AS chunk_id, source_type, source_id, chunk_text, event_at,
               (1.0 - ({vec_col} <=> CAST(:qvec AS halfvec({len(q_vec)})))) AS vec_score
        FROM knowledge_chunks
        WHERE patient_profile_id = CAST(:pid AS uuid)
          AND {vec_col} IS NOT NULL
        ORDER BY {vec_col} <=> CAST(:qvec AS halfvec({len(q_vec)}))
        LIMIT 25
        """
    )
    try:
        vec_rows = db.execute(vec_sql, {"pid": pid_str, "qvec": vec_literal}).mappings().all()
    except Exception:
        vec_rows = []

    # 2) Lexical BM25-style PostgreSQL tsvector ranking
    bm25_sql = text(
        """
        SELECT id::text AS chunk_id, source_type, source_id, chunk_text, event_at,
               ts_rank_cd(tsv, websearch_to_tsquery('english', :q)) AS bm25_score
        FROM knowledge_chunks
        WHERE patient_profile_id = CAST(:pid AS uuid)
          AND tsv @@ websearch_to_tsquery('english', :q)
        ORDER BY bm25_score DESC
        LIMIT 25
        """
    )
    try:
        bm25_rows = db.execute(bm25_sql, {"pid": pid_str, "q": expanded_query}).mappings().all()
    except Exception:
        bm25_rows = []

    # 3) Fuzzy BD Drug Catalog -> KnowledgeChunk Graph/Trigram Leg
    tokens = [tok.strip(",.?!") for tok in query.split() if len(tok.strip(",.?!")) >= 3]
    trgm_rows = []
    if tokens:
        matched_terms = set()
        for tok in tokens[:6]:
            cat_sql = text(
                """
                SELECT brand_name, generic_name,
                       GREATEST(similarity(LOWER(brand_name), LOWER(:tok)),
                                similarity(LOWER(generic_name), LOWER(:tok))) AS sim
                FROM bd_drug_catalog
                WHERE brand_name % :tok OR generic_name % :tok
                ORDER BY sim DESC
                LIMIT 3
                """
            )
            try:
                for mr in db.execute(cat_sql, {"tok": tok}).mappings().all():
                    if float(mr["sim"] or 0) >= 0.35:
                        matched_terms.add(mr["brand_name"])
                        matched_terms.add(mr["generic_name"])
            except Exception:
                pass
        if matched_terms:
            ilike_clauses = " OR ".join(f"chunk_text ILIKE :m{i}" for i in range(len(matched_terms)))
            params: Dict[str, Any] = {"pid": pid_str}
            for i, term in enumerate(matched_terms):
                params[f"m{i}"] = f"%{term}%"
            trgm_sql = text(
                f"""
                SELECT id::text AS chunk_id, source_type, source_id, chunk_text, event_at,
                       1.0 AS trgm_score
                FROM knowledge_chunks
                WHERE patient_profile_id = CAST(:pid AS uuid)
                  AND ({ilike_clauses})
                ORDER BY event_at DESC
                LIMIT 15
                """
            )
            try:
                trgm_rows = db.execute(trgm_sql, params).mappings().all()
            except Exception:
                trgm_rows = []

    # Fallback: if profile has chunks without active vector column yet, grab recent chunks so lexical/recency never returns empty
    if not vec_rows and not bm25_rows and not trgm_rows:
        fallback_sql = text(
            """
            SELECT id::text AS chunk_id, source_type, source_id, chunk_text, event_at, 0.25 AS vec_score
            FROM knowledge_chunks
            WHERE patient_profile_id = CAST(:pid AS uuid)
            ORDER BY event_at DESC
            LIMIT 15
            """
        )
        vec_rows = db.execute(fallback_sql, {"pid": pid_str}).mappings().all()

    # Combine via RRF + Exponential Temporal Decay
    candidates: Dict[str, Dict[str, Any]] = {}
    rrf_k = settings.rag_rrf_k
    lam = settings.rag_temporal_decay_lambda
    now = datetime.now(timezone.utc)

    def _register(rows, key_name: str, weight: float):
        for rank, row in enumerate(rows, start=1):
            cid = row["chunk_id"]
            if cid not in candidates:
                ev_at = row["event_at"]
                if ev_at and ev_at.tzinfo is None:
                    ev_at = ev_at.replace(tzinfo=timezone.utc)
                candidates[cid] = {
                    "chunk_id": cid,
                    "source_type": row["source_type"],
                    "source_id": str(row["source_id"]),
                    "chunk_text": row["chunk_text"],
                    "event_at": ev_at or now,
                    "vec_score": 0.0,
                    "bm25_score": 0.0,
                    "trgm_score": 0.0,
                    "rrf_score": 0.0,
                }
            candidates[cid][key_name] = float(row.get(key_name, 0.0) or 0.0)
            candidates[cid]["rrf_score"] += weight / (rrf_k + rank)

    _register(vec_rows, "vec_score", 1.0)
    _register(bm25_rows, "bm25_score", 0.9)
    _register(trgm_rows, "trgm_score", 0.8)

    for c in candidates.values():
        age_days = max(0.0, (now - c["event_at"]).total_seconds() / 86400.0)
        decay = math.exp(-lam * age_days)
        c["temporal_decay"] = round(decay, 4)
        c["rrf_decayed"] = c["rrf_score"] * decay

    top_fused = sorted(candidates.values(), key=lambda x: x["rrf_decayed"], reverse=True)[:20]

    reranker_label = "none"
    hits: List[RetrievalHit] = []
    if top_fused:
        docs = [c["chunk_text"] for c in top_fused]
        ranked_pairs, reranker_label = await provider.rerank(query, docs, top_k=top_k)
        for idx, rr_score in ranked_pairs[:top_k]:
            c = top_fused[idx]
            final = round(0.65 * float(rr_score) + 0.35 * min(1.0, c["rrf_decayed"] * 25.0), 4)
            hits.append(
                RetrievalHit(
                    chunk_id=c["chunk_id"],
                    source_type=c["source_type"],
                    source_id=c["source_id"],
                    citation=_citation_for(c["source_type"], c["source_id"], c["event_at"]),
                    chunk_text=c["chunk_text"],
                    event_at=c["event_at"].isoformat(),
                    vec_score=round(c["vec_score"], 4),
                    bm25_score=round(c["bm25_score"], 4),
                    trgm_score=round(c["trgm_score"], 4),
                    rrf_score=round(c["rrf_score"], 4),
                    temporal_decay=c["temporal_decay"],
                    rerank_score=round(float(rr_score), 4),
                    final_score=final,
                )
            )
        hits.sort(key=lambda h: h.final_score, reverse=True)

    trace = RetrievalTrace(
        query=query,
        expanded_query=expanded_query,
        embedding_backend=embed_label,
        reranker_backend=reranker_label,
        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        hits=hits,
    )
    TELEMETRY_STORE.record_rag(trace.model_dump())
    return trace
