import subprocess
import json
import os
import sys

def _transcribe_cloud(file_path: str, output_dir: str) -> dict:
    """Transcribe and diarize audio using Gemini Flash when TRANSCRIBE_MODE=cloud."""
    from google import genai
    from google.genai import types

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_LIVE_TEXT_MODEL", "gemini-3.8-flash")

    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    mime_map = {"wav": "audio/wav", "mp3": "audio/mp3", "m4a": "audio/mp4", "ogg": "audio/ogg", "webm": "audio/webm"}
    mime_type = mime_map.get(ext, "audio/wav")

    with open(file_path, "rb") as f:
        audio_bytes = f.read()

    prompt = (
        "Transcribe this conversation with speaker diarization (up to 2 speakers: SPEAKER_00, SPEAKER_01). "
        "Return ONLY valid JSON with key 'segments', where each item has "
        "'start' (float seconds), 'end' (float seconds), 'speaker' (string), and 'text' (string)."
    )
    resp = client.models.generate_content(
        model=model,
        contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type), prompt],
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    transcript_data = json.loads(resp.text or '{"segments": []}')

    base_name = os.path.splitext(os.path.basename(file_path))[0]
    json_output_path = os.path.join(output_dir, f"{base_name}.json")
    with open(json_output_path, "w", encoding="utf-8") as f:
        json.dump(transcript_data, f, ensure_ascii=False, indent=2)
    return transcript_data


def transcribe_audio(file_path: str, output_dir: str = "uploads/transcripts"):
    """
    Transcribe audio using WhisperX CLI (or Gemini cloud when TRANSCRIBE_MODE=cloud)
    with diarization and remove 'words' & 'word_segments' fields from the result.
    
    Args:
        file_path: Path to the audio file
        output_dir: Directory where WhisperX will save the output
    
    Returns:
        dict: Parsed transcript with diarization data (without 'words' or 'word_segments')
    """
    print("transcribe called")
    os.makedirs(output_dir, exist_ok=True)

    if os.getenv("TRANSCRIBE_MODE", "local").lower() == "cloud":
        return _transcribe_cloud(file_path, output_dir)

    cmd = [
        sys.executable,
        "-m",
        "whisperx",
        file_path,
        "--model", "medium",
        "--output_dir", output_dir,
        "--output_format", "json",
        "--diarize",
        "--language", "en",
        "--compute_type", "int8",
        "--diarize_model", "pyannote/speaker-diarization-3.0",
        "--max_speakers", "2",
    ]

    env = os.environ.copy()
    nvidia_root = os.path.join(
        sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages", "nvidia"
    )
    cuda_lib_dirs = [
        os.path.join(nvidia_root, "cublas", "lib"),
        os.path.join(nvidia_root, "cudnn", "lib"),
    ]
    existing_ld = env.get("LD_LIBRARY_PATH", "")
    env["LD_LIBRARY_PATH"] = ":".join([d for d in cuda_lib_dirs if os.path.isdir(d)] + ([existing_ld] if existing_ld else []))

    try:
        # Run WhisperX command
        subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)

        # Load WhisperX output JSON
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        json_output_path = os.path.join(output_dir, f"{base_name}.json")

        if not os.path.exists(json_output_path):
            raise FileNotFoundError(f"WhisperX output not found at {json_output_path}")

        with open(json_output_path, 'r', encoding='utf-8') as f:
            transcript_data = json.load(f)

        # Remove 'words' from each segment
        if "segments" in transcript_data:
            for segment in transcript_data["segments"]:
                segment.pop("words", None)

        # Remove top-level 'word_segments' field
        transcript_data.pop("word_segments", None)

        # (Optional) overwrite cleaned JSON file
        with open(json_output_path, 'w', encoding='utf-8') as f:
            json.dump(transcript_data, f, ensure_ascii=False, indent=2)

        return transcript_data

    except subprocess.CalledProcessError as e:
        print(f"WhisperX error: {e.stderr}")
        raise Exception(f"Transcription failed: {e.stderr}")
    except Exception as e:
        print(f"Error in transcription: {str(e)}")
        raise
