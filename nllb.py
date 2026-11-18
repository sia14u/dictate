"""NLLB-200 (distilled 600M, int8) offline translation via CTranslate2 + SentencePiece. Free, local."""
import glob, os, re, threading
import ctranslate2

CODES = {"en":"eng_Latn","ko":"kor_Hang","ja":"jpn_Jpan","zh":"zho_Hans","es":"spa_Latn","fr":"fra_Latn",
 "de":"deu_Latn","tl":"tgl_Latn","vi":"vie_Latn","ru":"rus_Cyrl","pt":"por_Latn","it":"ita_Latn",
 "ar":"arb_Arab","hi":"hin_Deva","th":"tha_Thai","id":"ind_Latn","tr":"tur_Latn","uk":"ukr_Cyrl",
 "nl":"nld_Latn","pl":"pol_Latn","sv":"swe_Latn","he":"heb_Hebr","fa":"pes_Arab","ms":"zsm_Latn",
 "el":"ell_Grek","cs":"ces_Latn","haw":"haw_Latn","sm":"smo_Latn","bn":"ben_Beng","ur":"urd_Arab",
 "ta":"tam_Taml","km":"khm_Khmr","lo":"lao_Laoo","my":"mya_Mymr","mn":"khk_Cyrl","ro":"ron_Latn",
 "hu":"hun_Latn","fi":"fin_Latn","da":"dan_Latn","no":"nob_Latn","nb":"nob_Latn","sw":"swh_Latn"}
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "nllb-600m-int8")
HF_ID = "facebook/nllb-200-distilled-600M"
_lock = threading.Lock(); _m = {}

def _load():
    if "t" not in _m:
        from transformers import AutoTokenizer
        _m["t"] = ctranslate2.Translator(MODEL_DIR, device="cpu", compute_type=os.environ.get("DICTATE_COMPUTE", "int16"), inter_threads=1,
                                         intra_threads=max(2, (os.cpu_count() or 4) - 2))
        _m["tok"] = AutoTokenizer.from_pretrained(MODEL_DIR if os.path.exists(os.path.join(MODEL_DIR, "tokenizer_config.json")) else HF_ID)
    return _m["t"], _m["tok"]

def supported(code): return code in CODES

_split = re.compile(r"(?<=[.!?。！？])\s+|\n+")
def translate(texts, src, dst):
    """texts: list[str] -> list[str]"""
    t, tok = _load()
    s, d = CODES[src], CODES[dst]
    # split long items into sentences to keep quality, then re-join
    flat, owners = [], []
    for i, tx in enumerate(texts):
        parts = [p for p in _split.split(tx.strip()) if p.strip()] or [""]
        for p in parts: flat.append(p); owners.append(i)
    tok.src_lang = s
    batch = [tok.convert_ids_to_tokens(tok.encode(p)) for p in flat]
    with _lock:
        res = t.translate_batch(batch, target_prefix=[[d]] * len(batch), beam_size=4, max_batch_size=16,
                                max_decoding_length=400)
    outs = [""] * len(texts)
    for o, r, src_text in zip(owners, res, flat):
        toks = [x for x in r.hypotheses[0] if x != d and x != "</s>"]
        piece = tok.decode(tok.convert_tokens_to_ids(toks), skip_special_tokens=True) if src_text.strip() else ""
        outs[o] = (outs[o] + " " + piece).strip()
    return outs
