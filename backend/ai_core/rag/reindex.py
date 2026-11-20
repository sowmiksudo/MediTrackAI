import argparse
import asyncio
from sqlalchemy.orm import Session

from ai_core.router import get_ai_provider
from db.database import SessionLocal
from db.models import KnowledgeChunk


async def reindex_chunks(target: str = "cloud") -> int:
    provider = get_ai_provider(mode_override="hybrid_gpu" if target == "bge_m3" else "cloud")
    db: Session = SessionLocal()
    updated = 0
    try:
        chunks = db.query(KnowledgeChunk).all()
        for ch in chunks:
            vec, sparse, _label = await provider.embed_text(ch.chunk_text)
            if len(vec) == 1024:
                ch.embedding_bge_m3 = vec
                if sparse:
                    ch.bge_sparse_weights = sparse
            elif len(vec) == 1536:
                ch.embedding_gemini_mm = vec
            updated += 1
        db.commit()
    finally:
        db.close()
    return updated


def main():
    parser = argparse.ArgumentParser(description="Backfill pgvector embeddings across KnowledgeChunks")
    parser.add_argument("--target", choices=["gemini", "bge_m3"], default="gemini")
    args = parser.parse_args()
    count = asyncio.run(reindex_chunks(args.target))
    print(f"Reindexed {count} chunks for target={args.target}")


if __name__ == "__main__":
    main()
