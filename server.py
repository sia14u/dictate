"""Dictate - local dictation, transcription and translation server.
Free/local stack: ffmpeg + faster-whisper (speech-to-text) + Argos Translate (offline MT)."""
import os, uuid, json, shutil, subprocess, threading, queue, time, traceback
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).parent
DATA = BASE / "data"; DATA.mkdir(exist_ok=True)
STATIC = BASE / "static"
DEFAULT_MODEL = os.environ.get("DICTATE_MODEL", "small")
ALLOWED_MODELS = {"tiny", "base", "small", "medium"}
MAX_BYTES = int(os.environ.get("DICTATE_MAX_MB", "2048")) * 1024 * 1024
PIN = os.environ.get("DICTATE_PIN", "")  # optional access code

app = FastAPI(title="Dictate")

LANGS = {"en":"English","ko":"Korean","ja":"Japanese","zh":"Chinese","es":"Spanish","fr":"French",
 "de":"German","tl":"Tagalog/Filipino","vi":"Vietnamese","ru":"Russian","pt":"Portuguese","it":"Italian",
 "ar":"Arabic","hi":"Hindi","th":"Thai","id":"Indonesian","tr":"Turkish","uk":"Ukrainian","nl":"Dutch",
 "pl":"Polish","sv":"Swedish","he":"Hebrew","fa":"Persian","ms":"Malay","el":"Greek","cs":"Czech"}

# ---------- auth (optional) ----------
@app.middleware("http")
async def pin_check(request: Request, call_next):
    if PIN and request.url.path.startswith("/api/") and request.url.path != "/api/health":
        if request.headers.get("x-dictate-pin") != PIN:
            return JSONResponse({"error": "PIN required"}, status_code=401)
    return await call_next(request)

# ---------- models ----------
_models, _mlock = {}, threading.Lock()
def get_model(name):
    name = name if name in ALLOWED_MODELS else DEFAULT_MODEL
    with _mlock:
        if name not in _models:
            from faster_whisper import WhisperModel
            _models[name] = WhisperModel(name, device="cpu", compute_type=os.environ.get("DICTATE_COMPUTE", "int16"),
                                         cpu_threads=max(2, (os.cpu_count() or 4) - 2))
        return _models[name]

_tlock = threading.Lock()
def installed_pairs():
    import argostranslate.translate as tr
    pairs = set()
    for l in tr.get_installed_languages():
        for t in l.translations_from:
            pairs.add((t.from_lang.code, t.to_lang.code))
    return pairs

def ensure_pair(src, dst):
    """Install an Argos pair on demand (free, offline after download)."""
    if (src, dst) in installed_pairs(): return True
    import argostranslate.package as p
    try:
        p.update_package_index()
        for a in p.get_available_packages():
            if a.from_code == src and a.to_code == dst:
                p.install_from_path(a.download()); return True
    except Exception: traceback.print_exc()
    return False

def translate_many(texts, src, dst, engine="nllb"):
    if src == dst: return list(texts)
    import nllb
    if engine != "argos" and nllb.supported(src) and nllb.supported(dst):
        return nllb.translate(list(texts), src, dst)
    return [translate_text(t, src, dst) for t in texts]

def translate_text(text, src, dst):
    text = (text or "").strip()
    if not text or src == dst: return text
    import argostranslate.translate as tr
    with _tlock:
        if src != "en" and dst != "en":  # pivot through English
            ok = ensure_pair(src, "en") and ensure_pair("en", dst)
            if not ok: raise RuntimeError(f"No free model for {src}->{dst}")
            return tr.translate(tr.translate(text, src, "en"), "en", dst)
        if not ensure_pair(src, dst): raise RuntimeError(f"No free model for {src}->{dst}")
        return tr.translate(text, src, dst)

def auto_target(src, target):
    if target and target != "auto": return target
    return "en" if src == "ko" else ("ko" if src == "en" else "en")

# ---------- ffmpeg ----------
def to_wav(src: Path) -> Path:
    out = src.with_suffix(".16k.wav")
    r = subprocess.run(["ffmpeg", "-nostdin", "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
                        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError("Could not read audio from this file (ffmpeg): " + (r.stderr or "no audio stream")[-400:])
    return out

def load_pcm(p: Path):
    import wave, numpy as np
    with wave.open(str(p)) as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0

def duration(p: Path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                           capture_output=True, text=True)
        return float(r.stdout.strip())
    except Exception: return None

# ---------- jobs ----------
JOBS = {}
Q = queue.Queue()

def run_job(job):
    try:
        job["status"] = "converting"
        wav = to_wav(Path(job["path"]))
        dur = duration(wav) or 0; job["duration"] = dur
        model = get_model(job["model"])
        job["status"] = "transcribing"
        lang = None if job["source"] in ("", "auto") else job["source"]
        pcm = load_pcm(wav)
        segs_iter, info = model.transcribe(pcm, language=lang, task="transcribe",
                                           vad_filter=True, beam_size=5)
        src = info.language; job["language"] = src; job["language_prob"] = round(info.language_probability, 3)
        segs = []
        for s in segs_iter:
            segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
            job["progress"] = min(0.99, s.end / dur) if dur else 0; job["segments"] = segs
        if job.get("strip"):  # live recording: drop spoken commands ("Dictate" / "Stop dictation")
            import re
            cmd = re.compile(r"^\s*(dictate|딕테이트|받아쓰기\s*시작)[.,!]?\s*|\s*\b(stop\s+dictat\w*|받아쓰기\s*(중지|끝|그만))[.,!]?\s*$", re.I)
            for s_ in segs: s_["text"] = cmd.sub("", s_["text"]).strip()
            segs[:] = [s_ for s_ in segs if s_["text"]]
        job["text"] = " ".join(s["text"] for s in segs).strip()
        if job.get("diarize") and segs:
            job["status"] = "diarizing"
            import diarize
            job["num_speakers"] = diarize.diarize(str(wav), segs, int(job.get("speakers") or 0))
            job["diarizer"] = diarize.ENGINE
        tgt = auto_target(src, job["target"]); job["target_resolved"] = tgt
        if tgt and tgt != src and tgt != "none":
            job["status"] = "translating"
            if job["engine"] in ("whisper", "auto") and tgt == "en":
                ts, _ = model.transcribe(pcm, language=src, task="translate", vad_filter=True, beam_size=5)
                raw = [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in ts]
                # align Whisper's English segments to the original segments by time (keeps speakers/side-by-side)
                tsegs = [{**s, "text": ""} for s in segs]
                for t in raw:
                    mid = (t["start"] + t["end"]) / 2
                    k = min(range(len(segs)), key=lambda i: 0 if segs[i]["start"] <= mid <= segs[i]["end"]
                            else min(abs(mid - segs[i]["start"]), abs(mid - segs[i]["end"]))) if segs else None
                    if k is not None: tsegs[k]["text"] = (tsegs[k]["text"] + " " + t["text"]).strip()
            else:
                outs = translate_many([s["text"] for s in segs], src, tgt, job["engine"])
                tsegs = [{**s, "text": o} for s, o in zip(segs, outs)]
            job["translation_segments"] = tsegs
            job["translation"] = " ".join(s["text"] for s in tsegs).strip()
        job["paragraphs"] = make_paragraphs(segs)
        if job.get("summary") and job["text"]:
            job["status"] = "summarizing"
            import summarize
            sl = job.get("summary_lang") or "en"
            sl = src if sl == "same" else sl
            spk = any(s.get("speaker") for s in segs)
            body = "\n".join((f'{p["speaker"]}: ' if spk else "") + p["text"] for p in job["paragraphs"])
            try:
                job["summary_md"] = summarize.summarize_with_actions(body, sl)
            except Exception as e:
                job["summary_error"] = str(e)
        job["progress"] = 1; job["status"] = "done"
    except Exception as e:
        traceback.print_exc(); job["status"] = "error"; job["error"] = str(e)
    finally:
        job["finished"] = time.time()
        try: shutil.rmtree(Path(job["path"]).parent, ignore_errors=True)
        except Exception: pass

def make_paragraphs(segs, gap=2.0, max_chars=700):
    """Clean transcript: merge segments into paragraphs on speaker change / long pause / length."""
    paras = []
    for i, s in enumerate(segs):
        p = paras[-1] if paras else None
        if (p and s.get("speaker") == p.get("speaker") and s["start"] - p["end"] < gap
                and len(p["text"]) + len(s["text"]) < max_chars):
            p["text"] += " " + s["text"]; p["end"] = s["end"]; p["segs"].append(i)
        else:
            paras.append({"start": s["start"], "end": s["end"], "speaker": s.get("speaker"),
                          "text": s["text"], "segs": [i]})
    return paras

def worker():
    while True:
        job = Q.get()
        run_job(job); Q.task_done()
threading.Thread(target=worker, daemon=True).start()

def cleanup_loop():
    while True:
        time.sleep(600); now = time.time()
        for k, j in list(JOBS.items()):
            if j.get("finished") and now - j["finished"] > 6 * 3600: JOBS.pop(k, None)
        for d in DATA.iterdir():
            if d.is_dir() and now - d.stat().st_mtime > 6 * 3600: shutil.rmtree(d, ignore_errors=True)
threading.Thread(target=cleanup_loop, daemon=True).start()

def enqueue(path, model, source, target, engine, opts=None):
    jid = path.parent.name
    job = {"id": jid, "path": str(path), "model": model or DEFAULT_MODEL, "source": source or "auto",
           "target": target or "auto", "engine": engine or "auto", "status": "queued", "progress": 0,
           "created": time.time(), **(opts or {})}
    JOBS[jid] = job; Q.put(job)
    return {"job_id": jid, "queue_position": Q.qsize()}

# ---------- API ----------
@app.get("/api/health")
def health():
    import summarize
    import tts
    return {"ok": True, "default_model": DEFAULT_MODEL, "pin": bool(PIN), "summary": summarize.available(),
            "tts_langs": sorted(tts.VOICES), "pyannote_token": bool(os.environ.get("HF_TOKEN"))}

@app.get("/api/languages")
def languages():
    import nllb
    return {"languages": {k: v for k, v in LANGS.items() if nllb.supported(k)}, "installed_pairs": sorted(f"{a}-{b}" for a, b in installed_pairs()),
            "models": sorted(ALLOWED_MODELS), "default_model": DEFAULT_MODEL}

@app.post("/api/upload")
async def upload(file: UploadFile = File(...), model: str = Form(DEFAULT_MODEL), source: str = Form("auto"),
                 target: str = Form("auto"), engine: str = Form("auto"),
                 diarize: str = Form("0"), speakers: int = Form(0),
                 summary: str = Form("0"), summary_lang: str = Form("en"), strip: str = Form("0")):
    """Single-request upload (files under ~95 MB through the tunnel)."""
    d = DATA / uuid.uuid4().hex[:12]; d.mkdir()
    ext = Path(file.filename or "audio").suffix[:10] or ".bin"
    p = d / ("input" + ext); size = 0
    with open(p, "wb") as f:
        while chunk := await file.read(1 << 20):
            size += len(chunk)
            if size > MAX_BYTES: shutil.rmtree(d); raise HTTPException(413, "File too large")
            f.write(chunk)
    o = _opts(diarize, speakers, summary, summary_lang); o["strip"] = strip == "1"
    return enqueue(p, model, source, target, engine, o)

# chunked upload for big videos (Cloudflare tunnels cap a single request at 100 MB)
@app.post("/api/chunk/start")
async def chunk_start(filename: str = Form(...)):
    d = DATA / uuid.uuid4().hex[:12]; d.mkdir()
    ext = Path(filename).suffix[:10] or ".bin"
    (d / "name").write_text("input" + ext)
    return {"upload_id": d.name}

@app.post("/api/chunk/{uid}")
async def chunk_put(uid: str, chunk: UploadFile = File(...)):
    d = DATA / uid
    if not d.is_dir() or not uid.isalnum(): raise HTTPException(404)
    p = d / (d / "name").read_text()
    with open(p, "ab") as f:
        while b := await chunk.read(1 << 20): f.write(b)
    if p.stat().st_size > MAX_BYTES: shutil.rmtree(d); raise HTTPException(413, "File too large")
    return {"ok": True, "size": p.stat().st_size}

@app.post("/api/chunk/{uid}/finish")
async def chunk_finish(uid: str, model: str = Form(DEFAULT_MODEL), source: str = Form("auto"),
                       target: str = Form("auto"), engine: str = Form("auto"),
                       diarize: str = Form("0"), speakers: int = Form(0),
                 summary: str = Form("0"), summary_lang: str = Form("en"), strip: str = Form("0")):
    d = DATA / uid
    if not d.is_dir() or not uid.isalnum(): raise HTTPException(404)
    o = _opts(diarize, speakers, summary, summary_lang); o["strip"] = strip == "1"
    return enqueue(d / (d / "name").read_text(), model, source, target, engine, o)

def _opts(diarize, speakers, summary, summary_lang):
    t = lambda v: str(v).lower() in ("1", "true", "on", "yes")
    return {"strip": False, "diarize": t(diarize), "speakers": max(0, min(int(speakers or 0), 10)),
            "summary": t(summary), "summary_lang": summary_lang or "en"}

@app.post("/api/summarize")
async def api_summarize(req: Request):
    body = await req.json()
    import summarize, asyncio
    try:
        md = await asyncio.to_thread(summarize.summarize_with_actions, body.get("text", ""), body.get("lang", "en"))
        return {"summary_md": md}
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/tts")
async def api_tts(req: Request):
    """Offline read-aloud (Piper). Returns audio/wav."""
    body = await req.json()
    import tts, asyncio
    from fastapi.responses import Response
    lang = body.get("lang", "en")
    if not tts.supported(lang): raise HTTPException(400, f"No offline voice for {lang}; use the device voice")
    try:
        wav = await asyncio.to_thread(tts.speak, body.get("text", ""), lang)
    except Exception as e:
        raise HTTPException(500, str(e))
    return Response(wav, media_type="audio/wav")

@app.post("/api/export/docx")
async def export_docx(req: Request):
    """Body: {title, paragraphs:[{label, text}], translation_title, translation:[{label,text}], summary_md}"""
    body = await req.json()
    from docx import Document
    from docx.shared import Pt
    import io, re
    from fastapi.responses import Response
    doc = Document()
    doc.add_heading(body.get("title") or "Transcript", 0)
    if body.get("summary_md"):
        for line in body["summary_md"].splitlines():
            line = line.rstrip()
            if not line: continue
            if line.startswith("#"): doc.add_heading(line.lstrip("# "), 1)
            elif re.match(r"^\s*[-*] ", line):
                doc.add_paragraph(re.sub(r"^\s*[-*] (\[ \] )?", "", line), style="List Bullet")
            else: doc.add_paragraph(line)
    def section(title, paras):
        if not paras: return
        doc.add_heading(title, 1)
        for p in paras:
            para = doc.add_paragraph()
            if p.get("label"):
                r = para.add_run(p["label"] + "  "); r.bold = True; r.font.size = Pt(10)
            para.add_run(p.get("text", ""))
    section("Transcript", body.get("paragraphs"))
    section(body.get("translation_title") or "Translation", body.get("translation"))
    buf = io.BytesIO(); doc.save(buf)
    return Response(buf.getvalue(), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    headers={"Content-Disposition": 'attachment; filename="transcript.docx"'})

@app.get("/api/job/{jid}")
def job(jid: str):
    j = JOBS.get(jid)
    if not j: raise HTTPException(404, "Unknown job")
    return {k: v for k, v in j.items() if k != "path"}

@app.post("/api/translate")
async def api_translate(req: Request):
    body = await req.json()
    text = body.get("text", ""); src = body.get("source", "auto"); tgt = body.get("target", "auto")
    if src in ("", "auto"):
        src = detect_lang(text)
    tgt = auto_target(src, tgt)
    try:
        out = translate_many([text], src, tgt, body.get("engine", "nllb"))[0]
        return {"source": src, "target": tgt, "translation": out}
    except Exception as e:
        raise HTTPException(400, str(e))

def detect_lang(text):
    import unicodedata
    counts = {"ko": 0, "ja": 0, "zh": 0, "ru": 0, "ar": 0, "th": 0, "latin": 0}
    for ch in text:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F: counts["ko"] += 1
        elif 0x3040 <= o <= 0x30FF: counts["ja"] += 1
        elif 0x4E00 <= o <= 0x9FFF: counts["zh"] += 1
        elif 0x0400 <= o <= 0x04FF: counts["ru"] += 1
        elif 0x0600 <= o <= 0x06FF: counts["ar"] += 1
        elif 0x0E00 <= o <= 0x0E7F: counts["th"] += 1
        elif ch.isalpha(): counts["latin"] += 1
    best = max(counts, key=counts.get)
    if counts["ja"] and best == "zh": best = "ja"
    return "en" if best == "latin" or counts[best] == 0 else best


@app.get("/")
def index(): return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

@app.get("/sw.js")
def sw(): return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache"})

app.mount("/", StaticFiles(directory=STATIC), name="static")
