#!/usr/bin/env bash
# One-time setup on a new machine (macOS Apple Silicon or Linux). Needs python3.11+ and ffmpeg (brew install ffmpeg python@3.12).
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "Please install ffmpeg first (macOS: brew install ffmpeg)"; exit 1; }
PY=$(command -v python3.12 || command -v python3.11 || command -v python3); "$PY" -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
mkdir -p models
python - <<'PY'
import os
from ctranslate2.converters import TransformersConverter
if not os.path.exists("models/nllb-600m-int8/model.bin"):
    TransformersConverter("facebook/nllb-200-distilled-600M",
        copy_files=["sentencepiece.bpe.model","tokenizer.json","tokenizer_config.json","special_tokens_map.json"]
    ).convert("models/nllb-600m-int8", quantization="int8", force=True)
if not os.path.exists("models/qwen2.5-1.5b-int8/model.bin"):
    TransformersConverter("Qwen/Qwen2.5-1.5B-Instruct",
        copy_files=["tokenizer.json","tokenizer_config.json","vocab.json","merges.txt","generation_config.json"]
    ).convert("models/qwen2.5-1.5b-int8", quantization="int8", force=True)
from faster_whisper import WhisperModel; WhisperModel("small", device="cpu", compute_type="int8")
import tts; tts._voice("en"); tts._voice("ko")
print("Models ready.")
PY
[ -f static/vosk/model-en.tar.gz ] || { mkdir -p static/vosk; curl -L -o static/vosk/vosk.js https://cdn.jsdelivr.net/npm/vosk-browser@0.0.8/dist/vosk.js;
  curl -L -o static/vosk/model-en.tar.gz https://ccoreilly.github.io/vosk-browser/models/vosk-model-small-en-us-0.15.tar.gz; }
echo "Done. Start with: ./start.sh   (on a Mac you can use DICTATE_COMPUTE=int8 for more speed)"
