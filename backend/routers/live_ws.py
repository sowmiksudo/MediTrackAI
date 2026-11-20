import asyncio
import base64
import io
import os
import re
import time
import uuid
import wave
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google.genai import types
from sqlalchemy import desc

from ai_core.rag.retriever import retrieve_hybrid_context
from ai_core.router import TELEMETRY_STORE, get_ai_provider
from auth.dependencies import resolve_ws_user_and_profile
from clinical.drug_verifier import lookup_bd_drug
from clinical.red_flag_gate import evaluate_text_red_flags
from db.database import SessionLocal
from db.models import ClinicalObservation, MedicationEpisode

router = APIRouter()

SAMPLE_RATE_IN = 16000
SILENCE_DURATION_SEC = 0.85
MIN_UTTERANCE_SEC = 0.35
BARGE_IN_DURATION_SEC = 0.35

_silero_model = None
_silero_tried = False


def _get_silero_vad():
    global _silero_model, _silero_tried
    if _silero_tried:
        return _silero_model
    _silero_tried = True
    try:
        import silero_vad  # type: ignore

        _silero_model = silero_vad.load_silero_vad()
    except Exception:
        _silero_model = None
    return _silero_model


class AdaptiveVad:
    """Uses Silero VAD v5 when available; otherwise adaptive noise-floor RMS gate (fan/room resilient)."""

    def __init__(self):
        self.silero = _get_silero_vad()
        self.noise_floor = 250.0
        self.engine_name = "silero_vad_v5" if self.silero is not None else "adaptive_noise_floor"

    def is_speech(self, pcm16: np.ndarray) -> bool:
        if pcm16.size == 0:
            return False
        if self.silero is not None and pcm16.size >= 512:
            try:
                import torch  # type: ignore

                f32 = pcm16[:512].astype(np.float32) / 32768.0
                prob = float(self.silero(torch.from_numpy(f32), SAMPLE_RATE_IN).item())
                return prob >= 0.58
            except Exception:
                pass
        rms = float(np.sqrt(np.mean(pcm16.astype(np.float32) ** 2)))
        threshold = max(420.0, self.noise_floor * 2.4)
        is_sp = rms >= threshold
        if not is_sp:
            self.noise_floor = 0.94 * self.noise_floor + 0.06 * min(rms, 600.0)
        return is_sp


def _pcm16_to_wav_bytes(pcm16: np.ndarray, sample_rate: int = SAMPLE_RATE_IN) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def _split_sentences(text: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?।])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _build_server_tools() -> List[types.Tool]:
    return [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name="search_patient_history",
                    description=(
                        "Search the patient's longitudinal medical history (prescriptions, lab reports, check-ins) "
                        "using bilingual Bangla/Banglish/English hybrid RAG."
                    ),
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "query": {"type": "STRING", "description": "Clinical or Banglish question to retrieve"},
                        },
                        "required": ["query"],
                    },
                ),
                types.FunctionDeclaration(
                    name="lookup_bd_drug",
                    description="Look up a Bangladeshi medication brand name or generic molecule in the DGDA catalog.",
                    parameters={
                        "type": "OBJECT",
                        "properties": {
                            "drug_name": {"type": "STRING", "description": "Brand or generic name e.g. Seclo, Bizoran, Comet"},
                        },
                        "required": ["drug_name"],
                    },
                ),
                types.FunctionDeclaration(
                    name="get_normalized_labs",
                    description="Fetch the patient's most recent normalized lab values (mmol/L, mg/dL, HbA1c, eGFR) and active medications.",
                    parameters={"type": "OBJECT", "properties": {}},
                ),
            ]
        )
    ]


@router.websocket("/ws/live")
async def live_voice_websocket(websocket: WebSocket):
    """Authenticated bilingual Bangla/Banglish/English Voice & Text Check-In WebSocket."""
    await websocket.accept()

    token = websocket.query_params.get("token")
    profile_id = websocket.query_params.get("profile_id")

    db = SessionLocal()
    try:
        user, profile = resolve_ws_user_and_profile(token, profile_id, db)
        profile_uuid = profile.id
        profile_name = profile.display_name
        profile_conditions = list(profile.chronic_conditions or [])
    except PermissionError as exc:
        await websocket.send_json({"type": "error", "detail": str(exc)})
        await websocket.close(code=4401)
        db.close()
        return

    provider = get_ai_provider()
    vad = AdaptiveVad()
    tools = _build_server_tools()

    system_instruction = (
        f"You are MediTrackAI, a warm, empathetic bilingual health companion conducting a check-in for patient '{profile_name}' "
        f"(known conditions: {', '.join(profile_conditions) or 'general wellness'}).\n"
        "LANGUAGE & STYLE:\n"
        "- The patient speaks Bangla, Banglish (mixed Bangla/English), or English. Reply naturally in the same language they use "
        "(warm conversational Bangla or gentle Banglish/English) in 2-4 concise sentences.\n"
        "- NEVER mention Hindi.\n"
        "- Use the provided tools (search_patient_history, lookup_bd_drug, get_normalized_labs) whenever the patient asks about "
        "their lab reports, sugar, pressure, creatinine, or Bangladeshi medicines (e.g. Seclo, Sergel, Bizoran, Comet, Napa).\n"
        "- Never provide a definitive medical diagnosis or prescribe/change medication doses — summarize observations and suggest discussing with their doctor.\n"
        "- If chest pain, breathing trouble, stroke symptoms, or severe bleeding are mentioned, immediately advise emergency ER care / Bangladesh 999."
    )

    history: List[types.Content] = []
    speech_chunks: List[np.ndarray] = []
    ptt_chunks: List[np.ndarray] = []
    ptt_active = False
    in_speech = False
    silence_samples = 0
    barge_in_samples = 0
    ai_task: Optional[asyncio.Task] = None
    ws_lock = asyncio.Lock()
    voice_name = "Aoede"

    async def send_json(payload: Dict[str, Any]) -> None:
        async with ws_lock:
            await websocket.send_json(payload)

    async def execute_server_tool(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.perf_counter()
        tool_db = SessionLocal()
        try:
            if name == "search_patient_history":
                query = str(args.get("query") or "recent health summary")
                trace = await retrieve_hybrid_context(tool_db, profile_uuid, query, top_k=5)
                citations = [h.citation for h in trace.hits]
                await send_json(
                    {
                        "type": "tool_event",
                        "tool": name,
                        "args": args,
                        "citations": citations,
                        "latency_ms": trace.latency_ms,
                    }
                )
                TELEMETRY_STORE.record_voice({"tool": name, "citations": citations, "latency_ms": trace.latency_ms})
                return {
                    "hits": [{"citation": h.citation, "text": h.chunk_text, "score": h.final_score} for h in trace.hits],
                    "citations": citations,
                }

            if name == "lookup_bd_drug":
                dname = str(args.get("drug_name") or "")
                matches = lookup_bd_drug(dname, tool_db, limit=3)
                latency = round((time.perf_counter() - t0) * 1000, 1)
                await send_json(
                    {
                        "type": "tool_event",
                        "tool": name,
                        "args": args,
                        "citations": [f"[DGDA: {m['brand_name']} -> {m['generic_name']}]" for m in matches],
                        "latency_ms": latency,
                    }
                )
                return {"matches": matches}

            if name == "get_normalized_labs":
                obs = (
                    tool_db.query(ClinicalObservation)
                    .filter(ClinicalObservation.patient_profile_id == profile_uuid)
                    .order_by(desc(ClinicalObservation.observed_at))
                    .limit(12)
                    .all()
                )
                meds = (
                    tool_db.query(MedicationEpisode)
                    .filter(MedicationEpisode.patient_profile_id == profile_uuid, MedicationEpisode.status == "active")
                    .all()
                )
                latency = round((time.perf_counter() - t0) * 1000, 1)
                await send_json(
                    {
                        "type": "tool_event",
                        "tool": name,
                        "args": {},
                        "citations": [f"[Obs: {len(obs)} labs, {len(meds)} active meds]"],
                        "latency_ms": latency,
                    }
                )
                return {
                    "recent_labs": [
                        {
                            "name": o.raw_name,
                            "value": o.canonical_value,
                            "unit": o.canonical_unit,
                            "flag": o.flag,
                            "date": o.observed_at.strftime("%Y-%m-%d") if o.observed_at else "",
                        }
                        for o in obs
                    ],
                    "active_medications": [
                        {
                            "brand": m.raw_brand_name,
                            "generic": m.generic_name,
                            "dosage": m.dosage,
                            "frequency": m.frequency_bd,
                        }
                        for m in meds
                    ],
                }
            return {"error": f"Unknown tool: {name}"}
        finally:
            tool_db.close()

    async def speak_text(text: str) -> None:
        for sentence in _split_sentences(text):
            pcm_bytes = await provider.synthesize_speech_pcm24k(sentence, voice_name=voice_name)
            if not pcm_bytes:
                continue
            byte_chunk = 9600
            for start in range(0, len(pcm_bytes), byte_chunk):
                b64 = base64.b64encode(pcm_bytes[start : start + byte_chunk]).decode("ascii")
                await send_json(
                    {
                        "serverContent": {
                            "modelTurn": {
                                "parts": [{"inlineData": {"mimeType": "audio/pcm", "data": b64}}]
                            }
                        }
                    }
                )

    async def process_turn(audio_pcm16: Optional[np.ndarray] = None, user_text: Optional[str] = None) -> None:
        try:
            asr_label = "text_input"
            if user_text is None and audio_pcm16 is not None:
                wav_bytes = _pcm16_to_wav_bytes(audio_pcm16, SAMPLE_RATE_IN)
                user_text, asr_label = await provider.transcribe_audio_bytes(wav_bytes, is_wav=True)
                if not user_text:
                    await send_json({"serverContent": {"turnComplete": True}})
                    return

            if not user_text:
                return

            await send_json({"type": "transcript", "role": "user", "text": user_text, "asr_engine": asr_label})

            # Red-flag deterministic safety check + Local PII redaction
            red_flags = evaluate_text_red_flags(user_text)
            if red_flags:
                await send_json({"type": "red_flag", "alerts": red_flags})

            pii_res = await provider.redact_pii(user_text)
            TELEMETRY_STORE.record_pii(pii_res.model_dump())
            await send_json({"type": "pii_diff", **pii_res.model_dump()})

            # Feed redacted text to LLM conversation history
            history.append(types.Content(role="user", parts=[types.Part.from_text(text=pii_res.redacted_text)]))

            # Multi-step server-side tool loop (up to 3 hops)
            response = None
            for _ in range(3):
                response = await provider.generate_text(
                    contents=history,
                    system_instruction=system_instruction,
                    tools=tools,
                    fast=True,
                )
                fcs = getattr(response, "function_calls", None) or []
                if not fcs:
                    break
                # Append model's tool call message
                if response.candidates and response.candidates[0].content:
                    history.append(response.candidates[0].content)
                tool_parts: List[types.Part] = []
                for fc in fcs:
                    res_data = await execute_server_tool(fc.name, dict(fc.args) if fc.args else {})
                    tool_parts.append(types.Part.from_function_response(name=fc.name, response=res_data))
                history.append(types.Content(role="user", parts=tool_parts))

            reply_text = (getattr(response, "text", None) or "").strip()
            if not reply_text and red_flags:
                reply_text = f"Emergency warning: {red_flags[0]['title']}. {red_flags[0]['action']}"

            if reply_text:
                history.append(types.Content(role="model", parts=[types.Part.from_text(text=reply_text)]))
                await send_json({"type": "transcript", "role": "assistant", "text": reply_text})
                await speak_text(reply_text)

            await send_json({"serverContent": {"turnComplete": True}})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await send_json({"type": "error", "detail": str(exc)})
            await send_json({"serverContent": {"turnComplete": True}})

    try:
        await send_json({"type": "ready", "profile": profile_name, "vad_engine": vad.engine_name, "mode": provider.mode_name})
        while True:
            msg = await websocket.receive_json()

            if "setup" in msg:
                setup = msg["setup"] or {}
                vn = (
                    setup.get("generation_config", {})
                    .get("speech_config", {})
                    .get("voice_config", {})
                    .get("prebuilt_voice_config", {})
                    .get("voice_name")
                )
                if vn:
                    voice_name = vn
                await send_json({"setupComplete": {}})
                continue

            if msg.get("type") == "ptt_start":
                ptt_active = True
                ptt_chunks = []
                if ai_task and not ai_task.done():
                    ai_task.cancel()
                continue

            if msg.get("type") == "ptt_end":
                ptt_active = False
                if ptt_chunks:
                    full_audio = np.concatenate(ptt_chunks)
                    ptt_chunks = []
                    if full_audio.size >= int(0.2 * SAMPLE_RATE_IN):
                        ai_task = asyncio.create_task(process_turn(audio_pcm16=full_audio))
                continue

            if msg.get("type") == "text_input":
                txt = str(msg.get("text") or "").strip()
                if txt:
                    if ai_task and not ai_task.done():
                        ai_task.cancel()
                    ai_task = asyncio.create_task(process_turn(user_text=txt))
                continue

            if "realtime_input" in msg:
                chunks = msg["realtime_input"].get("media_chunks", [])
                for chunk in chunks:
                    b64_data = chunk.get("data")
                    if not b64_data:
                        continue
                    pcm = np.frombuffer(base64.b64decode(b64_data), dtype=np.int16)
                    if pcm.size == 0:
                        continue

                    if ptt_active:
                        ptt_chunks.append(pcm)
                        continue

                    is_loud = vad.is_speech(pcm)
                    if ai_task is not None and not ai_task.done():
                        if is_loud:
                            barge_in_samples += pcm.size
                            if barge_in_samples >= int(BARGE_IN_DURATION_SEC * SAMPLE_RATE_IN):
                                ai_task.cancel()
                                ai_task = None
                                barge_in_samples = 0
                                await send_json({"serverContent": {"interrupted": True}})
                                in_speech = True
                                silence_samples = 0
                                speech_chunks = [pcm]
                        else:
                            barge_in_samples = 0
                        continue

                    if is_loud:
                        in_speech = True
                        silence_samples = 0
                        speech_chunks.append(pcm)
                    elif in_speech:
                        speech_chunks.append(pcm)
                        silence_samples += pcm.size
                        if silence_samples >= int(SILENCE_DURATION_SEC * SAMPLE_RATE_IN):
                            full_audio = np.concatenate(speech_chunks)
                            speech_chunks = []
                            in_speech = False
                            silence_samples = 0
                            if full_audio.size >= int(MIN_UTTERANCE_SEC * SAMPLE_RATE_IN):
                                ai_task = asyncio.create_task(process_turn(audio_pcm16=full_audio))
                continue

            if "client_content" in msg:
                cc = msg["client_content"] or {}
                if cc.get("turn_complete"):
                    turns = cc.get("turns", [])
                    texts = [
                        p.get("text", "")
                        for t in turns
                        for p in t.get("parts", [])
                        if p.get("text")
                    ]
                    combined = " ".join(texts).strip()
                    if combined:
                        if ai_task and not ai_task.done():
                            ai_task.cancel()
                        ai_task = asyncio.create_task(process_turn(user_text=combined))

    except WebSocketDisconnect:
        if ai_task and not ai_task.done():
            ai_task.cancel()
    finally:
        db.close()
