import asyncio
import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from ai_core.config import get_settings
from ai_core.providers.base import BaseAIProvider
from ai_core.schemas import PiiRedactionResult

T = TypeVar("T", bound=BaseModel)

_PHONE_RE = re.compile(r"(\+?880\s?-?1[3-9]\d{2}-?\d{6}|\b01[3-9]\d{8}\b)")
_NID_RE = re.compile(r"\b\d{10}\b|\b\d{13}\b|\b\d{17}\b")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def regex_pii_scrub(text: str) -> Tuple[str, List[str]]:
    masked: List[str] = []
    out = text
    if _PHONE_RE.search(out):
        out = _PHONE_RE.sub("[PHONE_REDACTED]", out)
        masked.append("PHONE_BD")
    if _NID_RE.search(out):
        out = _NID_RE.sub("[ID_REDACTED]", out)
        masked.append("NID_OR_REG")
    if _EMAIL_RE.search(out):
        out = _EMAIL_RE.sub("[EMAIL_REDACTED]", out)
        masked.append("EMAIL")
    return out, masked


class CloudGeminiProvider(BaseAIProvider):
    mode_name = "cloud"
    embed_column = "embedding_gemini_mm"
    embed_dims = 1536

    def __init__(self):
        self.settings = get_settings()
        api_key = self.settings.gemini_api_key or os.getenv("GEMINI_API_KEY", "")
        fast_http = types.HttpOptions(
            timeout=20000,
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        tts_http = types.HttpOptions(
            api_version="v1beta",
            timeout=20000,
            retry_options=types.HttpRetryOptions(attempts=1),
        )
        self.client = genai.Client(api_key=api_key, http_options=fast_http) if api_key else None
        self.tts_client = genai.Client(api_key=api_key, http_options=tts_http) if api_key else None

    def _require_client(self) -> genai.Client:
        if self.client is None:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        return self.client

    async def embed_text(self, text: str) -> Tuple[List[float], Optional[Dict[str, float]], str]:
        client = self._require_client()
        model = self.settings.gemini_embed_model

        def _run():
            resp = client.models.embed_content(
                model=model,
                contents=text[:8000],
                config=types.EmbedContentConfig(output_dimensionality=self.settings.gemini_embed_dims),
            )
            return list(resp.embeddings[0].values)

        vec = await asyncio.to_thread(_run)
        return vec, None, f"cloud:{model}(1536d)"

    async def embed_media(self, file_bytes: bytes, mime_type: str, caption: str = "") -> Optional[List[float]]:
        if not self.client:
            return None
        model = self.settings.gemini_embed_model

        def _run():
            parts = [types.Part.from_bytes(data=file_bytes, mime_type=mime_type)]
            if caption:
                parts.append(caption)
            resp = self.client.models.embed_content(
                model=model,
                contents=parts,
                config=types.EmbedContentConfig(output_dimensionality=self.settings.gemini_embed_dims),
            )
            return list(resp.embeddings[0].values)

        try:
            return await asyncio.to_thread(_run)
        except Exception:
            return None

    async def rerank(self, query: str, documents: List[str], top_k: int = 6) -> Tuple[List[Tuple[int, float]], str]:
        if not documents:
            return [], "cloud:none"
        if not self.client:
            return [(i, max(0.1, 1.0 - i * 0.05)) for i in range(min(top_k, len(documents)))], "fallback:order"

        class ScoreItem(BaseModel):
            index: int
            score: float

        class ScoreList(BaseModel):
            items: List[ScoreItem]

        doc_block = "\n".join(f"[{i}] {doc[:500]}" for i, doc in enumerate(documents))
        prompt = (
            "Score each medical record chunk (0.0 to 1.0) for clinical relevance to the user query "
            "(supports English, Bangla, and Banglish).\n"
            f"Query: {query}\n\nDocuments:\n{doc_block}"
        )
        try:
            res = await asyncio.wait_for(self.generate_structured(prompt, ScoreList, fast=True), timeout=12.0)
            ranked = sorted([(x.index, float(x.score)) for x in res.items if 0 <= x.index < len(documents)], key=lambda t: t[1], reverse=True)
            seen = {idx for idx, _ in ranked}
            for i in range(len(documents)):
                if i not in seen:
                    ranked.append((i, 0.1))
            return ranked[:top_k], f"cloud:{self.settings.gemini_fast_model}-rerank"
        except Exception:
            return [(i, max(0.1, 1.0 - i * 0.05)) for i in range(min(top_k, len(documents)))], "fallback:rrf_order"

    async def redact_pii(self, text: str) -> PiiRedactionResult:
        t0 = time.perf_counter()
        scrubbed, masked = regex_pii_scrub(text)
        # Lightweight Flash-Lite pass for personal names / Dhaka addresses if key present
        if self.client and len(text.strip()) > 10:
            class MaskedOut(BaseModel):
                redacted_text: str
                entities_masked: List[str]

            prompt = (
                "Mask ONLY personal identifiers (person names, street/house addresses, phone numbers, NIDs, emails) "
                "with placeholders like [PATIENT_NAME], [ADDRESS_REDACTED], [PHONE_REDACTED]. "
                "DO NOT mask medicines, symptoms, lab values, dates, or hospital names.\n\n"
                f"Text: {scrubbed}"
            )
            try:
                out = await self.generate_structured(prompt, MaskedOut, fast=True)
                return PiiRedactionResult(
                    raw_text=text,
                    redacted_text=out.redacted_text,
                    engine=f"cloud:{self.settings.gemini_fast_model}",
                    entities_masked=list(set(masked + out.entities_masked)),
                    latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                )
            except Exception:
                pass
        return PiiRedactionResult(
            raw_text=text,
            redacted_text=scrubbed,
            engine="regex_fast_mask",
            entities_masked=masked,
            latency_ms=round((time.perf_counter() - t0) * 1000, 1),
        )

    def _fallback_models(self, primary: str) -> List[str]:
        candidates = [
            primary,
            "gemini-3.1-flash-lite",
            self.settings.gemini_fast_model,
            self.settings.gemini_vlm_model,
        ]
        seen = set()
        out = []
        for m in candidates:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    def _call_with_fallback(self, client: genai.Client, primary: str, contents: Any, config: types.GenerateContentConfig):
        last_exc = None
        for m in self._fallback_models(primary):
            try:
                return client.models.generate_content(model=m, contents=contents, config=config)
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                if any(
                    code in msg
                    for code in ("503", "504", "429", "500", "404", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")
                ):
                    continue
                raise
        raise last_exc  # type: ignore[misc]

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        media_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        fast: bool = False,
    ) -> T:
        client = self._require_client()
        model = self.settings.gemini_fast_model if fast else self.settings.gemini_vlm_model
        contents: Any = [prompt]
        if media_bytes and mime_type:
            contents = [types.Part.from_bytes(data=media_bytes, mime_type=mime_type), prompt]

        def _run():
            cfg = types.GenerateContentConfig(
                temperature=0.0 if fast else 0.1,
                response_mime_type="application/json",
                response_schema=response_schema,
            )
            resp = self._call_with_fallback(client, model, contents, cfg)
            if getattr(resp, "parsed", None) is not None:
                return resp.parsed
            return response_schema.model_validate_json(resp.text)

        return await asyncio.to_thread(_run)

    async def generate_text(
        self,
        contents: Any,
        system_instruction: Optional[str] = None,
        tools: Any = None,
        fast: bool = False,
    ) -> Any:
        client = self._require_client()
        model = self.settings.gemini_fast_model if fast else self.settings.gemini_vlm_model
        cfg = types.GenerateContentConfig(
            system_instruction=system_instruction,
            tools=tools,
            temperature=0.4,
        )
        return await asyncio.to_thread(self._call_with_fallback, client, model, contents, cfg)

    async def synthesize_speech_pcm24k(self, text: str, voice_name: str = "Aoede") -> Optional[bytes]:
        if not self.tts_client or not text.strip():
            return None

        def _run():
            resp = self.tts_client.models.generate_content(
                model=self.settings.gemini_tts_model,
                contents=f"Say naturally and warmly: {text}",
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice_name)
                        )
                    ),
                ),
            )
            parts = resp.candidates[0].content.parts
            if parts and parts[0].inline_data:
                return parts[0].inline_data.data
            return None

        try:
            return await asyncio.to_thread(_run)
        except Exception:
            return None

    async def transcribe_audio_bytes(self, pcm16_or_wav: bytes, is_wav: bool = True) -> Tuple[str, str]:
        client = self._require_client()
        mime = "audio/wav" if is_wav else "audio/pcm"
        prompt = (
            "Transcribe this patient audio accurately. The speaker may speak Bengali (Bangla script), "
            "Banglish (mixed Bangla & English), or English, often mentioning Bangladeshi medicines or symptoms. "
            "Return ONLY the clean verbatim transcript text."
        )

        def _run():
            resp = self._call_with_fallback(
                client,
                self.settings.gemini_vlm_model,
                [types.Part.from_bytes(data=pcm16_or_wav, mime_type=mime), prompt],
                types.GenerateContentConfig(temperature=0.0),
            )
            return (resp.text or "").strip()

        text = await asyncio.to_thread(_run)
        return text, f"cloud:{self.settings.gemini_vlm_model}-asr"

    def get_telemetry(self) -> Dict[str, Any]:
        return {
            "inference_mode": "cloud",
            "active_vlm": self.settings.gemini_vlm_model,
            "active_fast": self.settings.gemini_fast_model,
            "active_embedder": f"{self.settings.gemini_embed_model} (1536d MRL)",
            "active_reranker": f"{self.settings.gemini_fast_model}-rerank",
            "active_asr": f"{self.settings.gemini_vlm_model} multimodal audio",
            "active_tts": self.settings.gemini_tts_model,
            "active_pii_scrubber": f"regex + {self.settings.gemini_fast_model}",
            "gpu_available": False,
            "vram": None,
        }
