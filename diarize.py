"""Free local speaker diarization: SpeechBrain ECAPA speaker embeddings + agglomerative clustering
over Whisper segments. No accounts/tokens needed (pyannote would need a gated HF token)."""
import os, threading, wave
import numpy as np

_m = {}; _lock = threading.Lock()
def _enc():
    with _lock:
        if "e" not in _m:
            from speechbrain.inference.speaker import EncoderClassifier
            _m["e"] = EncoderClassifier.from_hparams(
                source="speechbrain/spkrec-ecapa-voxceleb",
                savedir=os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "spkrec-ecapa"),
                run_opts={"device": "cpu"})
        return _m["e"]

def _read(wav_path):
    with wave.open(wav_path) as w:
        sr = w.getframerate(); a = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    return a.astype(np.float32) / 32768.0, sr

def _pyannote(wav_path, segments, num_speakers):
    """Used only when a free Hugging Face token is configured (HF_TOKEN or HUGGINGFACE_TOKEN env)."""
    tok = os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not tok: return None
    try:
        from pyannote.audio import Pipeline
        if "p" not in _m:
            try:
                _m["p"] = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=tok)
            except TypeError:
                _m["p"] = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=tok)
        kw = {"num_speakers": num_speakers} if num_speakers else {}
        ann = _m["p"](wav_path, **kw)
        ann = getattr(ann, "speaker_diarization", ann)  # pyannote 4 returns an output object
        turns = [(t.start, t.end, spk) for t, _, spk in ann.itertracks(yield_label=True)]
    except Exception as e:
        print("pyannote failed, falling back:", e); return None
    order = {}
    for s in segments:
        best, ov = None, 0
        for a, b, spk in turns:
            o = min(b, s["end"]) - max(a, s["start"])
            if o > ov: best, ov = spk, o
        if best is not None and best not in order: order[best] = len(order) + 1
        s["speaker"] = f"Speaker {order[best]}" if best is not None else (segments[0].get("speaker") or "Speaker 1")
    return len(order)

ENGINE = "speechbrain"
def diarize(wav_path, segments, num_speakers=0, threshold=0.75):
    global ENGINE
    n = _pyannote(wav_path, segments, num_speakers)
    if n is not None:
        ENGINE = "pyannote"; return n
    ENGINE = "speechbrain"
    return _speechbrain(wav_path, segments, num_speakers, threshold)

def _speechbrain(wav_path, segments, num_speakers=0, threshold=0.75):
    """Adds 'speaker' (e.g. 'Speaker 1') to each segment in place. Returns number of speakers."""
    import torch
    from sklearn.cluster import AgglomerativeClustering
    if not segments: return 0
    audio, sr = _read(wav_path); enc = _enc()
    embs, idx = [], []
    for i, s in enumerate(segments):
        a, b = int(s["start"] * sr), int(s["end"] * sr)
        if b - a < int(0.4 * sr):  # too short: pad around centre
            c = (a + b) // 2; a, b = max(0, c - int(0.4 * sr)), c + int(0.4 * sr)
        clip = audio[a:b]
        if len(clip) < int(0.2 * sr): continue
        with torch.no_grad():
            e = enc.encode_batch(torch.from_numpy(clip).unsqueeze(0)).squeeze().numpy()
        embs.append(e / (np.linalg.norm(e) + 1e-9)); idx.append(i)
    if not embs: return 0
    X = np.stack(embs)
    if len(X) == 1: labels = np.array([0])
    elif num_speakers and num_speakers > 0:
        labels = AgglomerativeClustering(n_clusters=min(num_speakers, len(X)), metric="cosine",
                                         linkage="average").fit_predict(X)
    else:
        labels = AgglomerativeClustering(n_clusters=None, distance_threshold=threshold, metric="cosine",
                                         linkage="average").fit_predict(X)
    order = {}
    for l in labels:
        if l not in order: order[l] = len(order) + 1
    lab = {i: f"Speaker {order[l]}" for i, l in zip(idx, labels)}
    last = "Speaker 1"
    for i, s in enumerate(segments):
        s["speaker"] = lab.get(i, last); last = s["speaker"]
    return len(order)
