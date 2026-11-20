#!/usr/bin/env bash
set -euo pipefail

# Provision RTX 5050 Hybrid Local GPU Runtime (Ollama MedGemma 4B Q4 + BGE-M3 + Qwen3-Reranker + Bangla Whisper + Silero VAD)
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="$ROOT_DIR/backend/venv/bin/python"
UV_BIN="$(command -v uv || true)"

echo "==> [1/4] Installing GPU Python dependencies (faster-whisper, FlagEmbedding, silero-vad, torch)..."
if [[ -n "$UV_BIN" ]]; then
  "$UV_BIN" pip install --python "$VENV_PY" -r "$ROOT_DIR/backend/requirements-gpu.txt"
else
  "$VENV_PY" -m pip install -r "$ROOT_DIR/backend/requirements-gpu.txt"
fi

echo "==> [2/4] Pulling MedGemma 4B Q4_K_M in Ollama (~2.9 GB VRAM)..."
if command -v ollama >/dev/null 2>&1; then
  # Pull community GGUF tag into local alias 'medgemma-4b-q4'
  ollama pull hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M
  ollama cp hf.co/unsloth/medgemma-4b-it-GGUF:Q4_K_M medgemma-4b-q4 || true
else
  echo "WARNING: Ollama binary not found. Install from https://ollama.com first."
fi

echo "==> [3/4] Pre-caching BGE-M3 (~1.1 GB VRAM), Qwen3-Reranker-0.6B (CPU), Silero VAD & Whisper..."
"$VENV_PY" - <<'PY'
from FlagEmbedding import BGEM3FlagModel
from transformers import AutoTokenizer, AutoModelForCausalLM
from faster_whisper import WhisperModel
import silero_vad

print("Caching BAAI/bge-m3...")
BGEM3FlagModel("BAAI/bge-m3", use_fp16=True)

print("Caching Qwen/Qwen3-Reranker-0.6B...")
AutoTokenizer.from_pretrained("Qwen/Qwen3-Reranker-0.6B")
AutoModelForCausalLM.from_pretrained("Qwen/Qwen3-Reranker-0.6B")

print("Caching faster-whisper large-v3-turbo...")
WhisperModel("large-v3-turbo", device="cpu", compute_type="int8")

print("Caching silero-vad...")
silero_vad.load_silero_vad()
print("All local GPU/CPU weights cached cleanly.")
PY

echo "==> [4/4] Done! Set INFERENCE_MODE=hybrid_gpu in backend/.env and run:"
echo "    cd backend && ./venv/bin/python -m ai_core.rag.reindex --target=bge_m3"
