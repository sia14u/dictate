"""Offline read-aloud with Piper (MIT/GPL voices on HF rhasspy/piper-voices). Voices download on first use."""
import io, os, threading, wave, urllib.request
VOICES = {"en": "en/en_US/lessac/medium/en_US-lessac-medium", "ko": "ko/ko_KR/kss/medium/ko_KR-kss-medium",
          "ja": "ja/ja_JP/hi_fi_captain/medium/ja_JP-hi_fi_captain-medium", "zh": "zh/zh_CN/huayan/medium/zh_CN-huayan-medium",
          "es": "es/es_ES/davefx/medium/es_ES-davefx-medium", "fr": "fr/fr_FR/siwis/medium/fr_FR-siwis-medium",
          "de": "de/de_DE/thorsten/medium/de_DE-thorsten-medium", "ru": "ru/ru_RU/irina/medium/ru_RU-irina-medium",
          "pt": "pt/pt_BR/faber/medium/pt_BR-faber-medium", "vi": "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium"}
DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "piper")
BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
_v = {}; _lock = threading.Lock()

def supported(lang): return lang in VOICES

def _voice(lang):
    from piper import PiperVoice
    if lang not in _v:
        os.makedirs(DIR, exist_ok=True)
        rel = VOICES[lang]; name = os.path.basename(rel)
        onnx = os.path.join(DIR, name + ".onnx")
        for ext in (".onnx", ".onnx.json"):
            p = os.path.join(DIR, name + ext)
            if not os.path.exists(p):
                urllib.request.urlretrieve(BASE + rel + ext, p + ".part"); os.replace(p + ".part", p)
        _v[lang] = PiperVoice.load(onnx)
    return _v[lang]

def speak(text, lang):
    with _lock:
        v = _voice(lang)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            v.synthesize_wav(text[:5000], w)
        return buf.getvalue()
