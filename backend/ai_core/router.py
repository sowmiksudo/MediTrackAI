from collections import deque
from functools import lru_cache
from typing import Any, Deque, Dict, Optional

from ai_core.config import get_settings
from ai_core.providers.base import BaseAIProvider
from ai_core.providers.cloud_gemini import CloudGeminiProvider
from ai_core.providers.local_gpu import LocalGPUProvider


class TelemetryStore:
    """In-memory ring buffer storing recent RAG retrieval & PII redaction traces for Judge Drawer."""

    def __init__(self, maxlen: int = 10):
        self.rag_traces: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.pii_diffs: Deque[Dict[str, Any]] = deque(maxlen=maxlen)
        self.voice_events: Deque[Dict[str, Any]] = deque(maxlen=20)

    def record_rag(self, trace: Dict[str, Any]) -> None:
        self.rag_traces.appendleft(trace)

    def record_pii(self, diff: Dict[str, Any]) -> None:
        self.pii_diffs.appendleft(diff)

    def record_voice(self, evt: Dict[str, Any]) -> None:
        self.voice_events.appendleft(evt)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "latest_rag": self.rag_traces[0] if self.rag_traces else None,
            "recent_rags": list(self.rag_traces)[:5],
            "latest_pii_diff": self.pii_diffs[0] if self.pii_diffs else None,
            "recent_voice_events": list(self.voice_events)[:8],
        }


TELEMETRY_STORE = TelemetryStore()


@lru_cache
def get_ai_provider(mode_override: Optional[str] = None) -> BaseAIProvider:
    settings = get_settings()
    mode = (mode_override or settings.inference_mode).lower()
    if mode == "hybrid_gpu":
        return LocalGPUProvider()
    return CloudGeminiProvider()
