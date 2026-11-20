import asyncio
import base64
import ctypes
import glob
import io
import os
import re
import sys
import uuid
import wave
from typing import Any, Dict, List, Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from google import genai
from google.genai import types

router = APIRouter()

# Lazy-loaded singletons so server startup stays fast and models load once.
_whisper_model: Optional[Any] = None
_kokoro_model: Optional[Any] = None
_model_lock = asyncio.Lock()

LIVE_VOICE_MODE = os.getenv("LIVE_VOICE_MODE", "local").lower()

KOKORO_MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "kokoro", "kokoro-v1.0.onnx"
)
KOKORO_VOICES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "kokoro", "voices-v1.0.bin"
)

VOICE_MAP = {
    "Aoede": "af_heart",
    "Puck": "am_michael",
    "Charon": "am_adam",
    "Kore": "af_bella",
    "Fenrir": "am_fenrir",
}

SAMPLE_RATE_IN = 16000
SPEECH_RMS_THRESHOLD = 500.0
SILENCE_DURATION_SEC = 0.8
MIN_UTTERANCE_SEC = 0.35
BARGE_IN_DURATION_SEC = 0.25


def _preload_cuda_libs() -> None:
    """Preload venv NVIDIA cuBLAS/cuDNN shared libs so CTranslate2 finds them without LD_LIBRARY_PATH."""
    nvidia_root = os.path.join(
        sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages", "nvidia"
    )
    for sub in ("cublas/lib/libcublas*.so*", "cudnn/lib/libcudnn*.so*"):
        for lib_path in sorted(glob.glob(os.path.join(nvidia_root, sub))):
            try:
                ctypes.CDLL(lib_path, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


async def _ensure_models() -> tuple[Any, Any]:
    """Load faster-whisper (CUDA) and Kokoro ONNX once when in local mode."""
    global _whisper_model, _kokoro_model
    if LIVE_VOICE_MODE == "cloud":
        return None, None
    async with _model_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel

            def _load_whisper() -> WhisperModel:
                _preload_cuda_libs()
                try:
                    print("Loading faster-whisper 'base' on CUDA...")
                    return WhisperModel("base", device="cuda", compute_type="float16")
                except Exception as exc:
                    print(f"CUDA faster-whisper init failed ({exc}); falling back to CPU int8")
                    return WhisperModel("base", device="cpu", compute_type="int8")

            _whisper_model = await asyncio.to_thread(_load_whisper)
            print("faster-whisper 'base' loaded.")

        if _kokoro_model is None:
            from kokoro_onnx import Kokoro

            def _load_kokoro() -> Kokoro:
                print(f"Loading Kokoro ONNX from {KOKORO_MODEL_PATH}...")
                return Kokoro(KOKORO_MODEL_PATH, KOKORO_VOICES_PATH)

            _kokoro_model = await asyncio.to_thread(_load_kokoro)
            print("Kokoro ONNX loaded.")

    return _whisper_model, _kokoro_model


def _pcm16_to_wav_bytes(pcm16: np.ndarray, sample_rate: int = SAMPLE_RATE_IN) -> bytes:
    """Wrap raw PCM16 mono samples in a WAV container for Gemini audio input."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def _convert_tools(setup_tools: Optional[List[Dict[str, Any]]]) -> Optional[List[types.Tool]]:
    """Convert Gemini Live setup functionDeclarations into google-genai Tool objects."""
    if not setup_tools:
        return None
    declarations: List[types.FunctionDeclaration] = []
    for tool_block in setup_tools:
        for fd in tool_block.get("functionDeclarations", []):
            declarations.append(
                types.FunctionDeclaration(
                    name=fd["name"],
                    description=fd.get("description", ""),
                    parameters=fd.get("parameters"),
                )
            )
    return [types.Tool(function_declarations=declarations)] if declarations else None


def _split_sentences(text: str) -> List[str]:
    """Split response text into speakable chunks for low-latency TTS streaming."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


@router.websocket("/ws/live")
async def live_voice_websocket(websocket: WebSocket):
    """Gemini-Live-compatible WebSocket powered by local faster-whisper + Kokoro ONNX + Gemini REST."""
    await websocket.accept()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key) if api_key else None
    tts_client = (
        genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
        if api_key
        else None
    )
    llm_model = os.getenv("GEMINI_LIVE_TEXT_MODEL", "gemini-3.8-flash")
    tts_model = os.getenv("GEMINI_LIVE_TTS_MODEL", "gemini-2.5-flash-preview-tts")

    system_instruction = "You are a helpful, empathetic medical assistant. Keep responses concise and conversational."
    tools: Optional[List[types.Tool]] = None
    kokoro_voice = "af_heart"
    gemini_voice = "Aoede"
    history: List[types.Content] = []

    speech_chunks: List[np.ndarray] = []
    in_speech = False
    silence_samples = 0
    barge_in_samples = 0
    ai_task: Optional[asyncio.Task] = None
    ws_lock = asyncio.Lock()

    async def send_json(payload: Dict[str, Any]) -> None:
        async with ws_lock:
            await websocket.send_json(payload)

    async def speak_text(text: str, kokoro: Any) -> None:
        """Synthesize text sentence-by-sentence and stream 24kHz PCM16 chunks."""
        for sentence in _split_sentences(text):
            if LIVE_VOICE_MODE == "cloud":
                if tts_client is None:
                    return
                tts_resp = await asyncio.to_thread(
                    tts_client.models.generate_content,
                    model=tts_model,
                    contents=sentence,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=gemini_voice
                                )
                            )
                        ),
                    ),
                )
                pcm_bytes = tts_resp.candidates[0].content.parts[0].inline_data.data
                byte_chunk = 9600
                for start in range(0, len(pcm_bytes), byte_chunk):
                    b64 = base64.b64encode(pcm_bytes[start : start + byte_chunk]).decode("ascii")
                    await send_json(
                        {
                            "serverContent": {
                                "modelTurn": {
                                    "parts": [
                                        {
                                            "inlineData": {
                                                "mimeType": "audio/pcm",
                                                "data": b64,
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    )
                continue

            samples, _sr = await asyncio.to_thread(
                kokoro.create, sentence, voice=kokoro_voice, speed=1.0, lang="en-us"
            )
            pcm16 = np.clip(samples * 32767.0, -32768, 32767).astype(np.int16)
            # Stream in ~200ms (4800 sample) chunks for smooth playback and fast barge-in
            chunk_size = 4800
            for start in range(0, len(pcm16), chunk_size):
                chunk_bytes = pcm16[start : start + chunk_size].tobytes()
                b64 = base64.b64encode(chunk_bytes).decode("ascii")
                await send_json(
                    {
                        "serverContent": {
                            "modelTurn": {
                                "parts": [
                                    {
                                        "inlineData": {
                                            "mimeType": "audio/pcm",
                                            "data": b64,
                                        }
                                    }
                                ]
                            }
                        }
                    }
                )

    async def process_turn(audio_pcm16: Optional[np.ndarray] = None, user_text: Optional[str] = None) -> None:
        """Transcribe audio (or send directly in cloud mode), query Gemini Flash, handle tool calls, and speak response."""
        try:
            whisper, kokoro = await _ensure_models()

            if user_text is None and audio_pcm16 is not None:
                if LIVE_VOICE_MODE == "cloud":
                    wav_bytes = _pcm16_to_wav_bytes(audio_pcm16, SAMPLE_RATE_IN)
                    history.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                                types.Part.from_text(text="Listen to the user's audio and respond."),
                            ],
                        )
                    )
                else:
                    audio_f32 = audio_pcm16.astype(np.float32) / 32768.0

                    def _transcribe() -> str:
                        segments, _info = whisper.transcribe(
                            audio_f32, beam_size=1, vad_filter=True
                        )
                        return " ".join(seg.text.strip() for seg in segments).strip()

                    user_text = await asyncio.to_thread(_transcribe)
                    if not user_text:
                        return
                    print(f"[LiveWS] User: {user_text}")
                    history.append(
                        types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
                    )
            elif user_text:
                print(f"[LiveWS] User: {user_text}")
                history.append(
                    types.Content(role="user", parts=[types.Part.from_text(text=user_text)])
                )
            else:
                return

            if client is None:
                reply = "Gemini API key is not configured on the backend."
                await speak_text(reply, kokoro)
                await send_json({"serverContent": {"turnComplete": True}})
                return

            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.7,
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=llm_model,
                contents=history,
                config=config,
            )

            if response.function_calls:
                fc_payload = []
                for fc in response.function_calls:
                    fc_payload.append(
                        {
                            "name": fc.name,
                            "args": dict(fc.args) if fc.args else {},
                            "id": getattr(fc, "id", None) or str(uuid.uuid4()),
                        }
                    )
                await send_json(
                    {"serverContent": {"modelTurn": {"functionCalls": fc_payload}}}
                )

            reply_text = (response.text or "").strip()
            if reply_text:
                print(f"[LiveWS] AI: {reply_text}")
                history.append(
                    types.Content(role="model", parts=[types.Part.from_text(text=reply_text)])
                )
                await speak_text(reply_text, kokoro)

            await send_json({"serverContent": {"turnComplete": True}})

        except asyncio.CancelledError:
            print("[LiveWS] AI turn cancelled (barge-in)")
            raise
        except Exception as exc:
            print(f"[LiveWS] Turn error: {exc}")
            await send_json({"serverContent": {"turnComplete": True}})

    try:
        while True:
            msg = await websocket.receive_json()

            if "setup" in msg:
                setup = msg["setup"] or {}
                sys_parts = setup.get("system_instruction", {}).get("parts", [])
                if sys_parts and sys_parts[0].get("text"):
                    system_instruction = sys_parts[0]["text"]

                tools = _convert_tools(setup.get("tools"))

                voice_name = (
                    setup.get("generation_config", {})
                    .get("speech_config", {})
                    .get("voice_config", {})
                    .get("prebuilt_voice_config", {})
                    .get("voice_name")
                )
                if voice_name in VOICE_MAP:
                    kokoro_voice = VOICE_MAP[voice_name]
                    gemini_voice = voice_name

                await _ensure_models()
                await send_json({"setupComplete": {}})
                continue

            if "realtime_input" in msg:
                chunks = msg["realtime_input"].get("media_chunks", [])
                for chunk in chunks:
                    b64_data = chunk.get("data")
                    if not b64_data:
                        continue
                    raw = base64.b64decode(b64_data)
                    pcm = np.frombuffer(raw, dtype=np.int16)
                    if pcm.size == 0:
                        continue

                    rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))
                    is_loud = rms >= SPEECH_RMS_THRESHOLD

                    # Barge-in if AI is currently speaking
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
                        if ai_task is not None and not ai_task.done():
                            ai_task.cancel()
                        ai_task = asyncio.create_task(process_turn(user_text=combined))

    except WebSocketDisconnect:
        if ai_task is not None and not ai_task.done():
            ai_task.cancel()
        print("[LiveWS] Client disconnected")
