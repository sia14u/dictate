"""End-to-end API test: python tests/e2e.py [base_url]

Expects sample media in tests/samples/ (not shipped in this repository).
"""
import sys, time, json, requests
B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
D = "tests/samples/"
def run(fn, **opts):
    t = time.time()
    with open(D + fn, "rb") as f:
        j = requests.post(B + "/api/upload", files={"file": (fn, f)}, data=opts).json()
    jid = j["job_id"]
    while True:
        r = requests.get(f"{B}/api/job/{jid}").json()
        if r["status"] in ("done", "error"): break
        time.sleep(1)
    r["_secs"] = round(time.time() - t, 1); return r
cases = sys.argv[2:] or None
tests = [("en.mp3", {}), ("ko.mp3", {}), ("ko_video.mp4", {"target": "en"}), ("en.m4a", {"target": "ja"}),
         ("two_voices.mov", {"diarize": "1", "summary": "1"}), ("en.wma", {"engine": "whisper", "target": "en"})]
for fn, o in tests:
    if cases and fn not in cases: continue
    r = run(fn, **o)
    print(f"\n=== {fn} {o} -> {r['status']} in {r['_secs']}s  lang={r.get('language')} ({r.get('language_prob')}) -> {r.get('target_resolved')} speakers={r.get('num_speakers')} {r.get('diarizer','')}")
    if r["status"] == "error": print("ERROR", r.get("error")); continue
    if o.get("diarize"):
        for p in r["paragraphs"]: print(f"  [{p['start']:5.1f}] {p.get('speaker')}: {p['text']}")
    else: print("  TEXT:", r["text"])
    print("  TRANSLATION:", r.get("translation"))
    if r.get("summary_md"): print("  SUMMARY:\n" + r["summary_md"])
