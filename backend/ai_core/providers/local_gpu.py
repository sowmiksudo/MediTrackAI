import asyncio
import json
import os
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

import httpx
from pydantic import BaseModel

from ai_core.config import get_settings
from ai_core.providers.base import BaseAIProvider
from ai_core.providers.cloud_gemini import CloudGeminiProvider, regex_pii_scrub
from ai_core.schemas import PiiRedactionResult

T = TypeVar("T", bound=BaseModel)


def _query_nvidia_smi() -> Optional[Dict[str, Any]]:
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader,nounits"],
            text=True,
            timeout=2,
        ).strip()
        if not out:
            return None
        name, used, total = [x.strip() for x in out.splitlines()[0].split(",")]
        return {"gpu_name": name, "used_mb": int(used), "total_mb": int(total)}
    except Exception:
        return None


class LocalGPUProvider(BaseAIProvider):
    """
    Hybrid Local GPU Provider (RTX 5050 8GB VRAM):
      - Local Ollama MedGemma 4B Q4 -> local PII/PHI redaction & red-flag pre-check
      - Local BGE-M3 -> 1024-dim dense+sparse embeddings
      - Local Qwen3-Reranker-0.6B (CPU ONNX/Torch) -> cross-encoder reranking
      - Local Bangla faster-whisper INT8 -> speech transcription
      - Cloud Gemini assist -> hard handwritten BD Rx VLM, longitudinal synthesis, Bangla TTS
    Gracefully falls back per-capability to CloudGeminiProvider if a local weight is not downloaded yet.
    """

    mode_name = "hybrid_gpu"
    embed_column = "embedding_bge_m3"
    embed_dims = 1024

    def __init__(self):
        self.settings = get_settings()
        self.cloud = CloudGeminiProvider()
        self._bge_model = None
        self._reranker_tokenizer = None
        self._reranker_model = None
        self._whisper_model = None
        self._ollama_ok: Optional[bool] = None
        self._loaded_components: Dict[str, str] = {}

    async def _check_ollama_model(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self.settings.ollama_base_url}/api/tags")
                if r.status_code != 200:
                    return False
                names = [m.get("name", "") for m in r.json().get("models", [])]
                target = self.settings.local_medgemma_model
                ok = any(target in n for n in names)
                self._ollama_ok = ok
                return ok
        except Exception:
            self._ollama_ok = False
            return False

    def _get_bge_m3(self):
        if self._bge_model is not None:
            return self._bge_model
        try:
            from FlagEmbedding import BGEM3FlagModel  # type: ignore

            self._bge_model = BGEM3FlagModel(self.settings.local_embed_model, use_fp16=True)
            self._loaded_components["embedder"] = f"local:{self.settings.local_embed_model}(FP16)"
            return self._bge_model
        except Exception:
            return None

    def _get_whisper(self):
        if self._whisper_model is not None:
            return self._whisper_model
        try:
            from faster_whisper import WhisperModel  # type: ignore

            try:
                self._whisper_model = WhisperModel(
                    self.settings.local_whisper_model, device="cuda", compute_type="int8"
                )
                self._loaded_components["asr"] = f"local:faster-whisper-{self.settings.local_whisper_model}(cuda-int8)"
            except Exception:
                self._whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
                self._loaded_components["asr"] = "local:faster-whisper-base(cpu-int8)"
            return self._whisper_model
        except Exception:
            return None

    def _get_reranker(self):
        if self._reranker_model is not None:
            return self._reranker_tokenizer, self._reranker_model
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore
            import torch

            tok = AutoTokenizer.from_pretrained(self.settings.local_reranker_model, local_files_only=True)
            mod = AutoModelForCausalLM.from_pretrained(
                self.settings.local_reranker_model, local_files_only=True, torch_dtype=torch.float32
            )
            mod.eval()
            self._reranker_tokenizer, self._reranker_model = tok, mod
            self._loaded_components["reranker"] = f"local:{self.settings.local_reranker_model}(CPU)"
            return tok, mod
        except Exception:
            return None, None

    async def embed_text(self, text: str) -> Tuple[List[float], Optional[Dict[str, float]], str]:
        bge = await asyncio.to_thread(self._get_bge_m3)
        if bge is not None:
            def _encode():
                out = bge.encode([text], return_dense=True, return_sparse=True, return_colbert_vecs=False)
                dense = [float(x) for x in out["dense_vecs"][0]]
                sparse = {str(k): float(v) for k, v in list(out["lexical_weights"][0].items())[:64]}
                return dense, sparse

            dense, sparse = await asyncio.to_thread(_encode)
            return dense, sparse, f"local:{self.settings.local_embed_model}(1024d)"

        # Fallback to Cloud embedder if local BGE-M3 weights aren't cached yet
        # Note: Cloud returns 1536d; caller routes to active embed_column
        vec, sparse, label = await self.cloud.embed_text(text)
        return vec, sparse, f"fallback->{label}"

    async def embed_media(self, file_bytes: bytes, mime_type: str, caption: str = "") -> Optional[List[float]]:
        return await self.cloud.embed_media(file_bytes, mime_type, caption)

    async def rerank(self, query: str, documents: List[str], top_k: int = 6) -> Tuple[List[Tuple[int, float]], str]:
        tok, mod = await asyncio.to_thread(self._get_reranker)
        if tok is not None and mod is not None and documents:
            import torch

            def _score():
                scores: List[Tuple[int, float]] = []
                yes_id = tok.convert_tokens_to_ids("yes")
                no_id = tok.convert_tokens_to_ids("no")
                for idx, doc in enumerate(documents):
                    prompt = f"Query: {query}\nDocument: {doc[:512]}\nRelevant:"
                    inputs = tok(prompt, return_tensors="pt", truncation=True, max_length=768)
                    with torch.no_grad():
                        logits = mod(**inputs).logits[0, -1]
                        probs = torch.softmax(torch.tensor([logits[no_id], logits[yes_id]]), dim=0)
                        scores.append((idx, float(probs[1].item())))
                scores.sort(key=lambda x: x[1], reverse=True)
                return scores[:top_k]

            try:
                ranked = await asyncio.to_thread(_score)
                return ranked, f"local:{self.settings.local_reranker_model}(CPU)"
            except Exception:
                pass
        ranked, label = await self.cloud.rerank(query, documents, top_k=top_k)
        return ranked, f"fallback->{label}"

    async def redact_pii(self, text: str) -> PiiRedactionResult:
        t0 = time.perf_counter()
        scrubbed, masked = regex_pii_scrub(text)
        if await self._check_ollama_model():
            prompt = (
                "Mask ONLY personal identifiers (person names, home addresses, phone numbers, NIDs) "
                "with [PATIENT_NAME], [ADDRESS_REDACTED], [PHONE_REDACTED]. "
                "Keep all symptoms, medicines, dosages, lab numbers, and hospital names intact. "
                "Return JSON: {\"redacted_text\": \"...\", \"entities_masked\": [...]}\n\n"
                f"Text: {scrubbed}"
            )
            try:
                async with httpx.AsyncClient(timeout=12.0) as client:
                    resp = await client.post(
                        f"{self.settings.ollama_base_url}/api/generate",
                        json={
                            "model": self.settings.local_medgemma_model,
                            "prompt": prompt,
                            "format": "json",
                            "stream": False,
                            "options": {"temperature": 0.0, "num_predict": 256},
                        },
                    )
                    if resp.status_code == 200:
                        data = json.loads(resp.json().get("response", "{}"))
                        if data.get("redacted_text"):
                            return PiiRedactionResult(
                                raw_text=text,
                                redacted_text=data["redacted_text"],
                                engine=f"local:ollama/{self.settings.local_medgemma_model}",
                                entities_masked=list(set(masked + list(data.get("entities_masked", [])))),
                                latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                            )
            except Exception:
                pass
        res = await self.cloud.redact_pii(text)
        res.engine = f"fallback->{res.engine}"
        return res

    async def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        media_bytes: Optional[bytes] = None,
        mime_type: Optional[str] = None,
        fast: bool = False,
    ) -> T:
        # Cloud Gemini handles hard handwritten Rx VLM and final structured synthesis cleanly
        return await self.cloud.generate_structured(
            prompt, response_schema, media_bytes=media_bytes, mime_type=mime_type, fast=fast
        )

    async def generate_text(
        self,
        contents: Any,
        system_instruction: Optional[str] = None,
        tools: Any = None,
        fast: bool = False,
    ) -> Any:
        return await self.cloud.generate_text(
            contents, system_instruction=system_instruction, tools=tools, fast=fast
        )

    async def synthesize_speech_pcm24k(self, text: str, voice_name: str = "Aoede") -> Optional[bytes]:
        return await self.cloud.synthesize_speech_pcm24k(text, voice_name=voice_name)

    async def transcribe_audio_bytes(self, pcm16_or_wav: bytes, is_wav: bool = True) -> Tuple[str, str]:
        whisper = await asyncio.to_thread(self._get_whisper)
        if whisper is not None:
            def _run():
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    tf.write(pcm16_or_wav)
                    path = tf.name
                try:
                    segs, _ = whisper.transcribe(
                        path,
                        beam_size=1,
                        vad_filter=True,
                        initial_prompt="Bangla Banglish health check-in, Napa, Sergel, Bizoran, Comet, HbA1c, pressure, sugar.",
                    )
                    return " ".join(s.text.strip() for s in segs).strip()
                finally:
                    if os.path.exists(path):
                        os.unlink(path)

            try:
                text = await asyncio.to_thread(_run)
                if text:
                    return text, self._loaded_components.get("asr", f"local:faster-whisper")
            except Exception:
                pass
        text, label = await self.cloud.transcribe_audio_bytes(pcm16_or_wav, is_wav=is_wav)
        return text, f"fallback->{label}"

    def get_telemetry(self) -> Dict[str, Any]:
        vram = _query_nvidia_smi()
        return {
            "inference_mode": "hybrid_gpu",
            "active_vlm": f"cloud:{self.settings.gemini_vlm_model} (Rx/Brief)",
            "active_fast": self.settings.gemini_fast_model,
            "active_embedder": self._loaded_components.get(
                "embedder", f"pending:{self.settings.local_embed_model} (fallback->gemini-embedding-2)"
            ),
            "active_reranker": self._loaded_components.get(
                "reranker", f"pending:{self.settings.local_reranker_model} (fallback->cloud)"
            ),
            "active_asr": self._loaded_components.get(
                "asr", f"pending:faster-whisper-{self.settings.local_whisper_model} (fallback->cloud)"
            ),
            "active_tts": self.settings.gemini_tts_model,
            "active_pii_scrubber": (
                f"local:ollama/{self.settings.local_medgemma_model}"
                if self._ollama_ok
                else f"pending:ollama/{self.settings.local_medgemma_model} (fallback->cloud)"
            ),
            "gpu_available": vram is not None,
            "vram": vram,
        }
