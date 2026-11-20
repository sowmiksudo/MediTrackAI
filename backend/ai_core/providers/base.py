from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar
from pydantic import BaseModel

from ai_core.schemas import PiiRedactionResult

T = TypeVar("T", bound=BaseModel)


class BaseAIProvider(ABC):
    mode_name: str = "base"
    embed_column: str = "embedding_gemini_mm"
    embed_dims: int = 1536

    @abstractmethod
    async def embed_text(self, text: str) -> Tuple[List[float], Optional[Dict[str, float]], str]:
        """Returns (dense_vector, optional_sparse_weights, backend_label)."""

    @abstractmethod
    async def embed_media(self, file_bytes: bytes, mime_type: str, caption: str = "") -> Optional[List[float]]:
        """Embeds image/PDF directly in multimodal space when supported."""

    @abstractmethod
    async def rerank(self, query: str, documents: List[str], top_k: int = 6) -> Tuple[List[Tuple[int, float]], str]:
        """Returns ([(doc_idx, score), ...], backend_label)."""

    @abstractmethod
    async def redact_pii(self, text: str) -> PiiRedactionResult:
        """Scrubs Bangladesh PII (names, +880 phones, NIDs, addresses) prior to external LLM synthesis."""

    @abstractmethod
    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        media_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        fast: bool = False,
    ) -> T:
        """Structured Pydantic output generation."""

    @abstractmethod
    async def generate_text(
        self,
        contents: Any,
        system_instruction: Optional[str] = None,
        tools: Any = None,
        fast: bool = False,
    ) -> Any:
        """Raw model call supporting tool calling."""

    @abstractmethod
    async def synthesize_speech_pcm24k(self, text: str, voice_name: str = "Aoede") -> Optional[bytes]:
        """Synthesize natural Bangla/English PCM16 24kHz audio."""

    @abstractmethod
    async def transcribe_audio_bytes(self, pcm16_or_wav: bytes, is_wav: bool = True) -> Tuple[str, str]:
        """Returns (transcript_text, backend_label)."""

    @abstractmethod
    def get_telemetry(self) -> Dict[str, Any]:
        """Live runtime status & hardware stats."""
