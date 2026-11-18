"""Free local summary (key points + action items) with Qwen2.5-1.5B-Instruct (int8, CTranslate2)."""
import os, threading
_m = {}; _lock = threading.Lock()
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "qwen2.5-1.5b-int8")
LANG_NAMES = {"en": "English", "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "es": "Spanish",
              "fr": "French", "de": "German", "tl": "Tagalog", "vi": "Vietnamese"}

def available(): return os.path.exists(os.path.join(MODEL_DIR, "model.bin"))

def _load():
    if "g" not in _m:
        import ctranslate2
        from transformers import AutoTokenizer
        _m["g"] = ctranslate2.Generator(MODEL_DIR, device="cpu", compute_type=os.environ.get("DICTATE_COMPUTE", "int16"),
                                        intra_threads=max(2, (os.cpu_count() or 4) - 2))
        _m["tok"] = AutoTokenizer.from_pretrained(MODEL_DIR)
    return _m["g"], _m["tok"]

def _gen(system, user, max_new=600):
    g, tok = _load()
    prompt = tok.apply_chat_template([{"role": "system", "content": system}, {"role": "user", "content": user}],
                                     tokenize=False, add_generation_prompt=True)
    ids = tok.convert_ids_to_tokens(tok.encode(prompt))
    r = g.generate_batch([ids], max_length=max_new, sampling_temperature=0.2, sampling_topk=1,
                         include_prompt_in_result=False, repetition_penalty=1.08)
    return tok.decode(r[0].sequences_ids[0], skip_special_tokens=True).strip()

SYS = ("You are a precise meeting/notes assistant. Only use facts stated in the transcript. "
       "Never invent names, dates or numbers.")

def summarize(text, lang="en"):
    if not available(): raise RuntimeError("Summary model not installed")
    lname = LANG_NAMES.get(lang, "English")
    with _lock:
        _, tok = _load()
        ids = tok.encode(text)
        CH = 2500
        if len(ids) > CH:  # map-reduce for long transcripts
            parts = [tok.decode(ids[i:i + CH]) for i in range(0, len(ids), CH)]
            notes = [_gen(SYS, "List the key points and any action items (tasks, who, when) in this transcript part "
                          "as short bullets:\n\n" + p, 400) for p in parts]
            text = "\n".join(notes)
        return _gen(SYS,
            "Summarize this transcript in English. Copy names and places exactly as written in the transcript. "
            "Use exactly this Markdown format (write 2-4 sentences under Summary):\n"
            "## Summary\n...\n\n## Key points\n- ...\n\n## Action items\n- [ ] task (owner, due date if stated)\n"
            "Action items are things a person commits to or is asked to do (e.g. 'I will send...', 'please call...'); "
            "list each with who will do it (use the speaker label) and when, if stated. "
            "Only if nobody commits to anything write '- None stated'.\n\nTranscript:\n" + text)

import re as _re
_COMMIT = _re.compile(r"\b(I'll|I will|we'll|we will|I'm going to|we're going to|let's|please|need to|needs to|have to|must|"
                      r"remind me|don't forget|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next week))\b|"
                      r"(할게요|하겠습니다|해야|해 주세요|해주세요|보낼게|보내겠습니다|드릴게요|까지)", _re.I)

def extract_actions(lines):
    """Rule-based fallback: sentences where someone commits to / is asked to do something."""
    out = []
    for line in lines:
        spk, _, body = line.partition(": ") if _re.match(r"^[^:]{1,40}: ", line) else ("", "", line)
        for sent in _re.split(r"(?<=[.!?。？！])\s+", body):
            if _COMMIT.search(sent) and len(sent) > 8:
                out.append(f"- [ ] {sent.strip()}" + (f" ({spk})" if spk else ""))
    return out

def _translate_md(md, lang):
    """Summaries are generated in English (best for the small model) then translated line by line with NLLB."""
    import nllb
    if lang == "en" or not nllb.supported(lang): return md
    lines = md.splitlines(); idx, texts, pref = [], [], []
    for i, l in enumerate(lines):
        m = _re.match(r"^(\s*#+\s*|\s*[-*]\s*(\[ \]\s*)?)?(.*)$", l)
        if m.group(3).strip():
            idx.append(i); pref.append(m.group(1) or ""); texts.append(m.group(3))
    outs = nllb.translate(texts, "en", lang)
    for i, p, o in zip(idx, pref, outs): lines[i] = p + o
    return "\n".join(lines)

def summarize_with_actions(text, lang="en"):
    md = summarize(text, "en")
    head, sep, tail = md.partition("## Action")
    if not sep or _re.search(r"none stated|없음", tail, _re.I) or "- " not in tail:
        acts = extract_actions(text.splitlines())
        if acts:
            title = "## Action items" if not sep else "## Action" + tail.splitlines()[0]
            md = head.rstrip() + "\n\n" + title + "\n" + "\n".join(acts[:15]) + "\n"
    return _translate_md(md, lang)
