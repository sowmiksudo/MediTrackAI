from functools import lru_cache
from typing import List, Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    inference_mode: Literal["hybrid_gpu", "cloud"] = "cloud"
    database_url: str = "postgresql://meditrack:meditrack@localhost:5433/meditrack"
    pg_port: int = 5433

    jwt_secret: str = "dev-jwt-secret-change-in-prod"
    file_signing_secret: str = "dev-file-signing-secret-change-in-prod"
    jwt_expire_minutes: int = 1440
    frontend_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080,https://dev-server.tenstral.com"

    host: str = "0.0.0.0"
    port: int = 8000
    upload_dir: str = "uploads"

    # Cloud Gemini Models
    gemini_api_key: str = ""
    gemini_vlm_model: str = "gemini-3.8-flash"
    gemini_fast_model: str = "gemini-3.5-flash-lite"
    gemini_embed_model: str = "gemini-embedding-2"
    gemini_tts_model: str = "gemini-2.5-flash-preview-tts"
    gemini_embed_dims: int = 1536
    cohere_api_key: str = ""

    # Hybrid Local GPU Models
    ollama_base_url: str = "http://localhost:11434"
    local_medgemma_model: str = "medgemma-4b-q4"
    local_whisper_model: str = "large-v3-turbo"
    local_embed_model: str = "BAAI/bge-m3"
    local_embed_dims: int = 1024
    local_reranker_model: str = "Qwen/Qwen3-Reranker-0.6B"

    # Hybrid RAG Parameters
    rag_rrf_k: int = 60
    rag_temporal_decay_lambda: float = 0.005
    rag_top_k: int = 6

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
