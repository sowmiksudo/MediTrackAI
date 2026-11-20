import asyncio
import json
import os
from typing import Dict, Any

from ai_core.router import get_ai_provider


def transcribe_audio(file_path: str, output_dir: str = "uploads/transcripts") -> Dict[str, Any]:
    """
    Transcribe bilingual Bangla/Banglish/English audio via dual-mode AI provider
    (local Bangla faster-whisper in hybrid_gpu mode, Gemini multimodal audio in cloud mode).
    """
    os.makedirs(output_dir, exist_ok=True)
    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    provider = get_ai_provider()
    text, engine = asyncio.run(provider.transcribe_audio_bytes(audio_bytes, is_wav=True))
    transcript_data = {
        "engine": engine,
        "segments": [{"start": 0.0, "end": 0.0, "speaker": "SPEAKER_00", "text": text}],
        "text": text,
    }
    base_name = os.path.splitext(os.path.basename(file_path))[0]
    json_output_path = os.path.join(output_dir, f"{base_name}.json")
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)
    return transcript_data
