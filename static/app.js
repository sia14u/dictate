"use strict";
const $ = (id) => document.getElementById(id);
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const WAKE = /\bdictate\b|딕테이트|받아쓰기\s*시작/i;
const STOP = /\bstop\s+dictat\w*|받아쓰기\s*(중지|끝|그만)/i;
const SPEAK_LANGS = [["en-US","English (US)"],["ko-KR","한국어 Korean"],["ja-JP","日本語 Japanese"],["zh-CN","中文 Chinese"],
  ["es-ES","Español"],["fr-FR","Français"],["de-DE","Deutsch"],["fil-PH","Filipino"],["vi-VN","Tiếng Việt"],
  ["ru-RU","Русский"],["pt-BR","Português"],["it-IT","Italiano"],["th-TH","ไทย Thai"],["hi-IN","हिन्दी Hindi"],
  ["id-ID","Bahasa Indonesia"],["ar-SA","العربية"],["tr-TR","Türkçe"],["uk-UA","Українська"]];
let PIN = localStorage.getItem("dictatePin") || "";
let HEALTH = {}, LANGS = {};
let result = null, speakerNames = {};

// ---------- helpers ----------
function toast(msg, ms = 2600) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(t._h); t._h = setTimeout(() => t.hidden = true, ms); }
async function api(path, opts = {}) {
  opts.headers = Object.assign({}, opts.headers || {}, PIN ? { "x-dictate-pin": PIN } : {});
  const r = await fetch(path, opts);
  if (r.status === 401) { PIN = prompt("Enter your Dictate access PIN") || ""; localStorage.setItem("dictatePin", PIN); return api(path, opts); }
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m; } catch (e) {} throw new Error(m); }
  return r;
}
const short = (bcp) => { const s = bcp.split("-")[0]; return s === "fil" ? "tl" : s; };
const langName = (c) => LANGS[c] || c || "";
function fmtTime(t, sep = ",") { t = Math.max(0, t || 0); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = Math.floor(t % 60), ms = Math.round((t % 1) * 1000);
  return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}${sep}${String(ms).padStart(3,"0")}`; }
const clock = (t) => fmtTime(t).slice(0, 8);
const esc = (s) => (s || "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
const spkName = (s) => s ? (speakerNames[s] || s) : "";
function setPill(cls, text) { const p = $("pill"); p.className = "pill " + cls; p.textContent = text; }
function opt(id) { return $(id).type === "checkbox" ? $(id).checked : $(id).value; }
function saveOpts() { const o = {}; ["speakLang","targetLang","optClean","optTimes","optDiar","optSpk","optSum","optModel","optEngine","optSumLang","optRecord","optWake","optVoice"].forEach(k => o[k] = opt(k)); localStorage.setItem("dictateOpts", JSON.stringify(o)); }
function loadOpts() { try { const o = JSON.parse(localStorage.getItem("dictateOpts") || "{}"); for (const k in o) { const el = $(k); if (!el) continue; if (el.type === "checkbox") el.checked = o[k]; else el.value = o[k]; } } catch (e) {} }

function makeParagraphs(segs, gap = 2.0, maxChars = 700) {
  const paras = [];
  segs.forEach((s, i) => { const p = paras[paras.length - 1];
    if (p && s.speaker === p.speaker && s.start - p.end < gap && p.text.length + s.text.length < maxChars) { p.text += " " + s.text; p.end = s.end; p.segs.push(i); }
    else paras.push({ start: s.start, end: s.end, speaker: s.speaker, text: s.text, segs: [i] }); });
  return paras;
}

// ---------- render ----------
function aligned() { return result && result.translation_segments && result.translation_segments.length === result.segments.length; }
function units() {
  // returns [{start,end,speaker,text,tr}] in the current view (paragraphs or segments)
  if (!result) return [];
  const segs = result.segments || [], trs = result.translation_segments || [];
  if (opt("optClean")) {
    const paras = makeParagraphs(segs);
    return paras.map(p => ({ ...p, tr: aligned() ? p.segs.map(i => trs[i].text).join(" ") : null }));
  }
  return segs.map((s, i) => ({ ...s, tr: aligned() ? trs[i].text : null }));
}
function label(u) { const a = []; if (opt("optTimes")) a.push(`[${clock(u.start)}]`); if (u.speaker) a.push(spkName(u.speaker) + ":"); return a.join(" "); }
function render() {
  if (!result) { $("results").hidden = true; return; }
  $("results").hidden = false;
  const us = units();
  const html = (key) => us.map(u => { const t = key === "orig" ? u.text : u.tr; if (t == null) return "";
    return `<p>${opt("optTimes") ? `<span class="ts">${clock(u.start)}</span>` : ""}${u.speaker ? `<span class="spk">${esc(spkName(u.speaker))}</span>` : ""}${esc(t)}</p>`; }).join("");
  $("orig").innerHTML = html("orig") || `<p>${esc(result.text || "")}</p>`;
  $("tr").innerHTML = aligned() ? html("tr") : (result.translation ? `<p>${esc(result.translation)}</p>` : `<p class="hint">${result.target_resolved === "none" ? "Translation off" : "(no translation yet)"}</p>`);
  $("origLang").textContent = result.language ? `· ${langName(result.language)}` : "";
  $("trLang").textContent = result.target_resolved && result.target_resolved !== "none" ? `· ${langName(result.target_resolved)}` : "";
  const meta = []; if (result.duration) meta.push(clock(result.duration)); if (result.num_speakers) meta.push(`${result.num_speakers} speaker(s) · ${result.diarizer || ""}`);
  if (result.language_prob) meta.push(`detected ${langName(result.language)} ${Math.round(result.language_prob * 100)}%`);
  $("meta").textContent = meta.join(" · ");
  // speakers
  const spks = [...new Set((result.segments || []).map(s => s.speaker).filter(Boolean))];
  $("speakers").hidden = !spks.length;
  $("speakers").innerHTML = spks.map(s => `<input data-spk="${esc(s)}" value="${esc(spkName(s))}" aria-label="Rename ${esc(s)}">`).join("") + (spks.length ? `<span class="hint">← tap to rename speakers</span>` : "");
  $("speakers").querySelectorAll("input").forEach(inp => inp.addEventListener("change", () => { speakerNames[inp.dataset.spk] = inp.value.trim() || inp.dataset.spk; render(); }));
  // summary
  $("summaryBox").hidden = !(result.summary_md || result.summary_error);
  const named = (result.summary_md || "").replace(/(Speaker|스피커)\s?(\d+)/g, (m, w, n) => speakerNames["Speaker " + n] || m);
  $("summaryBox").innerHTML = result.summary_md ? mdToHtml(named) : `<p class="hint">Summary failed: ${esc(result.summary_error || "")}</p>`;
}
function mdToHtml(md) {
  let out = "", inList = false;
  md.split("\n").forEach(l => { l = l.trimEnd();
    if (/^\s*[-*] /.test(l)) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${esc(l.replace(/^\s*[-*] /, "").replace(/^\[ \]\s*/, "☐ "))}</li>`; return; }
    if (inList) { out += "</ul>"; inList = false; }
    if (/^#+ /.test(l)) out += `<h3>${esc(l.replace(/^#+ /, ""))}</h3>`; else if (l) out += `<p>${esc(l.replace(/\*\*/g, ""))}</p>`; });
  return out + (inList ? "</ul>" : "");
}

// ---------- exports ----------
function sumNamed() { return (result.summary_md || "").replace(/(Speaker|스피커)\s?(\d+)/g, (m, w, n) => speakerNames["Speaker " + n] || m); }
function download(name, data, type) { const b = data instanceof Blob ? data : new Blob([data], { type }); const a = document.createElement("a");
  a.href = URL.createObjectURL(b); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500); }
function plain(key) { return units().map(u => { const t = key === "orig" ? u.text : u.tr; const l = label(u); return t == null ? "" : (l ? l + " " : "") + t; }).filter(Boolean).join(opt("optClean") ? "\n\n" : "\n"); }
function trPlain() { return aligned() ? plain("tr") : (result.translation || ""); }
function exportAs(fmt) {
  if (!result) return; const which = opt("expWhich"); const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  const base = `dictate-${stamp}`; const sum = sumNamed();
  const oL = langName(result.language) || "Original", tL = langName(result.target_resolved) || "Translation";
  if (fmt === "txt") {
    let s = sum ? sumNamed().replace(/^#+ /gm, "").replace(/^- \[ \] /gm, "- ") + "\n\n" : "";
    if (which !== "tr") s += (which === "both" ? `=== ${oL} ===\n` : "") + plain("orig") + "\n\n";
    if (which !== "orig" && trPlain()) s += (which === "both" ? `=== ${tL} ===\n` : "") + trPlain() + "\n";
    return download(base + ".txt", s, "text/plain;charset=utf-8");
  }
  if (fmt === "md") {
    const mdu = (key) => units().map(u => { const t = key === "orig" ? u.text : u.tr; if (t == null) return "";
      return `${opt("optTimes") ? "`" + clock(u.start) + "` " : ""}${u.speaker ? `**${spkName(u.speaker)}:** ` : ""}${t}`; }).filter(Boolean).join("\n\n");
    let s = `# Transcript — ${new Date().toLocaleString()}\n\n` + (sum ? sum + "\n\n" : "");
    if (which !== "tr") s += `## ${oL}\n\n` + mdu("orig") + "\n\n";
    if (which !== "orig" && trPlain()) s += `## ${tL}\n\n` + (aligned() ? mdu("tr") : result.translation) + "\n";
    return download(base + ".md", s, "text/markdown;charset=utf-8");
  }
  if (fmt === "srt" || fmt === "vtt") {
    const segs = result.segments || [], trs = result.translation_segments || [];
    const useTr = which === "tr" && trs.length; const list = useTr ? trs : segs;
    let s = fmt === "vtt" ? "WEBVTT\n\n" : "";
    list.forEach((c, i) => { let txt = c.text; const sp = (segs[i] || {}).speaker;
      if (which === "both" && aligned()) txt += "\n" + trs[i].text;
      if (sp) txt = (fmt === "vtt" ? `<v ${spkName(sp)}>` : `${spkName(sp)}: `) + txt;
      const sep = fmt === "vtt" ? "." : ",";
      s += (fmt === "srt" ? `${i + 1}\n` : "") + `${fmtTime(c.start, sep)} --> ${fmtTime(Math.max(c.end, c.start + 0.5), sep)}\n${txt}\n\n`; });
    return download(`${base}.${fmt}`, s, fmt === "vtt" ? "text/vtt;charset=utf-8" : "application/x-subrip;charset=utf-8");
  }
  if (fmt === "docx") {
    const mk = (key) => units().map(u => ({ label: label(u), text: key === "orig" ? u.text : u.tr })).filter(p => p.text != null);
    const body = { title: `Transcript — ${new Date().toLocaleString()}`, summary_md: sum,
      paragraphs: which !== "tr" ? mk("orig") : [], translation_title: tL,
      translation: which !== "orig" ? (aligned() ? mk("tr") : (result.translation ? [{ label: "", text: result.translation }] : [])) : [] };
    api("/api/export/docx", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
      .then(r => r.blob()).then(b => download(base + ".docx", b)).catch(e => toast("DOCX failed: " + e.message));
  }
}

// ---------- read aloud ----------
async function sayColumn(key) {
  if (!result) return; const text = $(key).innerText.trim(); if (!text) return;
  const lang = key === "orig" ? result.language : result.target_resolved;
  if (opt("optVoice") === "piper" && (HEALTH.tts_langs || []).includes(lang)) {
    try { toast("Generating voice…", 1500);
      const r = await api("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, lang }) });
      const a = new Audio(URL.createObjectURL(await r.blob())); a.play(); return; } catch (e) { toast("Piper failed, using device voice"); }
  }
  if (!window.speechSynthesis) return toast("No speech voice available");
  speechSynthesis.cancel(); const u = new SpeechSynthesisUtterance(text);
  const bcp = (SPEAK_LANGS.find(([c]) => short(c) === lang) || [lang])[0]; u.lang = bcp;
  const v = speechSynthesis.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith(lang)); if (v) u.voice = v;
  speechSynthesis.speak(u);
}

// ---------- jobs (files + recorded sessions) ----------
function jobForm(extra = {}) {
  const f = new FormData(); const sl = opt("optSumLang");
  Object.entries({ model: opt("optModel"), target: opt("targetLang"), engine: opt("optEngine"), diarize: opt("optDiar") ? "1" : "0",
    speakers: opt("optSpk"), summary: opt("optSum") ? "1" : "0", summary_lang: sl, ...extra }).forEach(([k, v]) => f.append(k, v));
  return f;
}
function progress(p, text) { $("progWrap").hidden = false; $("progBar").style.width = Math.round(p * 100) + "%"; $("progText").textContent = text; }
async function submitMedia(blob, name, source = "auto", strip = false) {
  setPill("busy", "Working…"); progress(0, "Uploading…");
  let jid; const CH = 45 * 1024 * 1024;
  try {
    if (blob.size <= 90 * 1024 * 1024) {
      const f = jobForm({ source, strip: strip ? "1" : "0" }); f.append("file", blob, name);
      jid = (await (await api("/api/upload", { method: "POST", body: f })).json()).job_id;
    } else {
      const sf = new FormData(); sf.append("filename", name);
      const uid = (await (await api("/api/chunk/start", { method: "POST", body: sf })).json()).upload_id;
      for (let off = 0; off < blob.size; off += CH) {
        const cf = new FormData(); cf.append("chunk", blob.slice(off, off + CH), "part");
        await api(`/api/chunk/${uid}`, { method: "POST", body: cf });
        progress(off / blob.size * 0.3, `Uploading… ${Math.round(off / blob.size * 100)}%`);
      }
      jid = (await (await api(`/api/chunk/${uid}/finish`, { method: "POST", body: jobForm({ source, strip: strip ? "1" : "0" }) })).json()).job_id;
    }
  } catch (e) { setPill("idle", "Idle"); progress(0, "Upload failed: " + e.message); return; }
  const labels = { queued: "Waiting in line", converting: "Extracting audio (ffmpeg)", transcribing: "Transcribing (Whisper)",
    diarizing: "Finding speakers", translating: "Translating", summarizing: "Writing summary" };
  while (true) {
    await new Promise(r => setTimeout(r, 1500));
    let j; try { j = await (await api(`/api/job/${jid}`)).json(); } catch (e) { continue; }
    progress(j.progress || 0, `${labels[j.status] || j.status}…${j.duration ? " (" + clock(j.duration) + " audio)" : ""}`);
    if (j.segments && j.status === "transcribing") { result = j; render(); }
    if (j.status === "done") { result = j; speakerNames = {}; render(); progress(1, "Done ✓"); setPill(armed ? "armed" : "idle", armed ? "Listening for “Dictate”" : "Idle"); return j; }
    if (j.status === "error") { progress(0, "Error: " + j.error); setPill("idle", "Idle"); toast(j.error, 6000); return; }
  }
}

// ---------- live dictation ----------
let rec = null, armed = false, dictating = false, startIdx = 0, wakeIdx = -1, done = new Set(), t0 = 0, lastEnd = 0;
let mediaRec = null, chunks = [], liveBlob = null, stream = null, wakeEngine = "webspeech";
let vosk = null;

function newLiveResult() {
  const src = short(opt("speakLang"));
  result = { source: "live", language: src, segments: [], translation_segments: [], target_resolved: resolveTarget(src) }; speakerNames = {};
}
function resolveTarget(src) { const t = opt("targetLang"); if (t === "none") return "none"; if (t !== "auto") return t; return src === "ko" ? "en" : (src === "en" ? "ko" : "en"); }

async function addFinal(text) {
  text = text.trim(); if (!text) return;
  const now = (Date.now() - t0) / 1000; const seg = { start: lastEnd, end: now, text }; lastEnd = now;
  const i = result.segments.push(seg) - 1; result.translation_segments[i] = { ...seg, text: "…" }; render();
  const tgt = result.target_resolved; if (tgt === "none" || tgt === result.language) { result.translation_segments[i].text = tgt === "none" ? "" : text; render(); return; }
  try { const r = await (await api("/api/translate", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source: result.language, target: tgt, engine: opt("optEngine") === "argos" ? "argos" : "nllb" }) })).json();
    result.translation_segments[i].text = r.translation; } catch (e) { result.translation_segments[i].text = "(translation failed)"; }
  render();
}

async function beginDictation() {
  if (dictating) return; dictating = true; t0 = Date.now(); lastEnd = 0; newLiveResult(); render();
  $("micBtn").classList.add("rec"); setPill("rec", "● Dictating — say “Stop dictation”"); $("liveAfter").hidden = true;
  if (navigator.vibrate) navigator.vibrate(60);
  if (opt("optRecord") || wakeEngine === "vosk" || !SR) await startRecording();
  if (wakeEngine === "vosk" || !SR) $("interim").textContent = "Recording… text appears after you stop (Whisper).";
}
async function endDictation() {
  if (!dictating) return; dictating = false; $("micBtn").classList.remove("rec"); $("interim").textContent = "";
  setPill(armed ? "armed" : "idle", armed ? "Listening for “Dictate”" : "Idle");
  const hadRecorder = !!mediaRec; await stopRecording();
  if (!armed && rec) { try { rec.stop(); } catch (e) {} }
  if ((wakeEngine === "vosk" || !SR) && liveBlob) { submitMedia(liveBlob, "dictation" + blobExt(liveBlob), short(opt("speakLang")), true); return; }
  $("liveAfter").hidden = !(result && (result.segments.length || hadRecorder));
  $("processRec").hidden = !liveBlob;
}
function blobExt(b) { return /mp4|m4a|aac/.test(b.type) ? ".m4a" : /ogg/.test(b.type) ? ".ogg" : /wav/.test(b.type) ? ".wav" : ".webm"; }
async function startRecording() {
  try {
    stream = stream && stream.active ? stream : await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const types = ["audio/webm;codecs=opus", "audio/mp4", "audio/ogg;codecs=opus", "audio/webm"]; const type = types.find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t));
    mediaRec = new MediaRecorder(stream, type ? { mimeType: type } : undefined); chunks = []; liveBlob = null;
    mediaRec.ondataavailable = (e) => e.data.size && chunks.push(e.data); mediaRec.start(1000);
  } catch (e) { mediaRec = null; toast("Mic recording unavailable: " + e.message); }
}
function stopRecording() {
  return new Promise(res => { if (!mediaRec) return res();
    mediaRec.onstop = () => { liveBlob = new Blob(chunks, { type: mediaRec.mimeType || "audio/webm" }); mediaRec = null;
      if (!armed || wakeEngine !== "vosk") { stream && stream.getTracks().forEach(t => t.stop()); stream = null; } res(); };
    try { mediaRec.stop(); } catch (e) { mediaRec = null; res(); } });
}

function startRecognizer() {
  if (!SR) return false; if (rec) return true;
  rec = new SR(); rec.lang = opt("speakLang"); rec.continuous = true; rec.interimResults = true; done = new Set(); startIdx = 0; wakeIdx = dictating ? 0 : -1;
  rec.onresult = (e) => {
    let interim = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const r = e.results[i]; let txt = r[0].transcript;
      if (!dictating) {
        if (armed && WAKE.test(txt)) { wakeIdx = i; beginDictation(); } else { interim = "heard: " + txt; continue; }
      }
      if (i < startIdx || (wakeIdx >= 0 && i < wakeIdx) || done.has(i)) continue;
      if (i === wakeIdx) { const parts = txt.split(WAKE); txt = parts[parts.length - 1]; }
      const m = txt.match(STOP);
      if (m) { done.add(i); addFinal(txt.slice(0, m.index)); endDictation(); return; }
      if (r.isFinal) { done.add(i); addFinal(txt); } else interim += txt;
    }
    $("interim").textContent = interim;
    window._lastLen = e.results.length;
  };
  rec.onerror = (e) => { if (e.error === "not-allowed" || e.error === "service-not-allowed") { toast("Microphone/speech permission denied"); armed = false; updateWakeBtn(); } };
  rec.onend = () => { rec = null; if (armed || dictating) setTimeout(() => { if ((armed || dictating) && !rec) startRecognizer(); }, 250); };
  try { rec.start(); } catch (e) { rec = null; return false; }
  return true;
}

// Offline wake word (Vosk WASM, English grammar)
async function startVosk() {
  if (vosk) return true;
  setPill("busy", "Loading offline wake word…");
  if (!window.Vosk) await new Promise((res, rej) => { const s = document.createElement("script"); s.src = "/vosk/vosk.js"; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
  const model = await Vosk.createModel(location.origin + "/vosk/model-en.tar.gz");
  stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 } });
  const ctx = new (window.AudioContext || window.webkitAudioContext)();
  const recog = new model.KaldiRecognizer(ctx.sampleRate, JSON.stringify(["dictate", "stop dictation", "stop", "[unk]"]));
  recog.on("result", (m) => { const t = (m.result && m.result.text) || "";
    if (!dictating && /\bdictate\b/.test(t)) beginDictation(); else if (dictating && /stop/.test(t)) endDictation(); });
  const src = ctx.createMediaStreamSource(stream); const node = ctx.createScriptProcessor(4096, 1, 1);
  node.onaudioprocess = (ev) => { try { recog.acceptWaveform(ev.inputBuffer); } catch (e) {} };
  src.connect(node); node.connect(ctx.destination);
  vosk = { model, ctx, node, src, recog }; return true;
}
function stopVosk() { if (!vosk) return; try { vosk.node.disconnect(); vosk.src.disconnect(); vosk.ctx.close(); vosk.model.terminate(); } catch (e) {} vosk = null; stream && stream.getTracks().forEach(t => t.stop()); stream = null; }

function updateWakeBtn() { $("wakeBtn").textContent = armed ? "👂 Hands-free: On" : "👂 Hands-free: Off"; $("wakeBtn").classList.toggle("on", armed);
  if (!dictating) setPill(armed ? "armed" : "idle", armed ? "Listening for “Dictate”" : "Idle"); }
async function toggleWake() {
  armed = !armed; const pref = opt("optWake"); wakeEngine = pref === "auto" ? (SR ? "webspeech" : "vosk") : pref;
  if (wakeEngine === "webspeech" && !SR) wakeEngine = "vosk";
  if (armed) {
    try { if (wakeEngine === "vosk") await startVosk(); else if (!startRecognizer()) throw new Error("Speech recognition failed to start"); }
    catch (e) { armed = false; toast("Hands-free unavailable: " + e.message, 5000); }
  } else { stopVosk(); if (rec && !dictating) { try { rec.stop(); } catch (e) {} } }
  updateWakeBtn();
}
async function toggleMic() {
  if (dictating) return endDictation();
  wakeEngine = armed ? wakeEngine : ((opt("optWake") === "vosk" || !SR) ? "vosk" : "webspeech");
  if (wakeEngine === "webspeech") { wakeIdx = window._lastLen || 0; startIdx = wakeIdx; if (!rec) { startRecognizer(); startIdx = 0; wakeIdx = 0; } }
  await beginDictation();
}

// ---------- init ----------
async function init() {
  SPEAK_LANGS.forEach(([c, n]) => $("speakLang").add(new Option(n, c)));
  if (navigator.language && navigator.language.startsWith("ko")) $("speakLang").value = "ko-KR";
  try { HEALTH = await (await api("/api/health")).json(); const L = await (await api("/api/languages")).json(); LANGS = L.languages; } catch (e) { toast("Server not reachable: " + e.message, 6000); }
  $("targetLang").add(new Option("Auto (English ⇄ Korean)", "auto")); $("targetLang").add(new Option("No translation", "none"));
  Object.entries(LANGS).forEach(([c, n]) => $("targetLang").add(new Option(n, c)));
  loadOpts();
  if (!HEALTH.summary) { $("optSum").disabled = true; $("optSum").parentElement.title = "Summary model not installed"; }
  if (!SR) $("liveHint").innerHTML = "This browser has no built-in speech recognition, so hands-free uses the offline <b>Vosk</b> wake word and text appears after you stop (Whisper). Say <b>“Dictate”</b> / <b>“Stop dictation”</b>, or tap the mic.";
  document.querySelectorAll("select,input[type=checkbox]").forEach(el => el.addEventListener("change", () => { saveOpts(); if (["optClean","optTimes"].includes(el.id)) render();
    if (el.id === "speakLang" && rec) { try { rec.stop(); } catch (e) {} } }));
  document.querySelectorAll(".tab").forEach(b => b.addEventListener("click", () => { document.querySelectorAll(".tab").forEach(x => x.classList.toggle("active", x === b));
    $("tab-live").hidden = b.dataset.tab !== "live"; $("tab-file").hidden = b.dataset.tab !== "file"; }));
  $("wakeBtn").onclick = toggleWake; $("micBtn").onclick = toggleMic;
  $("clearBtn").onclick = () => { result = null; render(); $("liveAfter").hidden = true; };
  $("processRec").onclick = () => liveBlob && submitMedia(liveBlob, "dictation" + blobExt(liveBlob), short(opt("speakLang")), true);
  $("sumLive").onclick = async () => { if (!result) return; toast("Summarizing (local model)…", 4000);
    try { const sl = opt("optSumLang") === "same" ? result.language : opt("optSumLang");
      const r = await (await api("/api/summarize", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: plain("orig"), lang: sl }) })).json();
      result.summary_md = r.summary_md; render(); } catch (e) { toast("Summary failed: " + e.message); } };
  $("fileIn").onchange = (e) => { const f = e.target.files[0]; if (f) submitMedia(f, f.name, "auto"); e.target.value = ""; };
  const drop = $("drop");
  ["dragover","dragenter"].forEach(ev => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
  ["dragleave","drop"].forEach(ev => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
  drop.addEventListener("drop", (e) => { const f = e.dataTransfer.files[0]; if (f) submitMedia(f, f.name, "auto"); });
  document.querySelectorAll("[data-copy]").forEach(b => b.onclick = () => navigator.clipboard.writeText($(b.dataset.copy).innerText).then(() => toast("Copied")));
  document.querySelectorAll("[data-say]").forEach(b => b.onclick = () => sayColumn(b.dataset.say));
  document.querySelectorAll("[data-exp]").forEach(b => b.onclick = () => exportAs(b.dataset.exp));
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(() => {});
  if (!window.isSecureContext) toast("Open this page over HTTPS for microphone access", 6000);
}
init();
