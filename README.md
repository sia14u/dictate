# Dictate

A free, local web app to dictate, transcribe, translate, label speakers, and summarize audio and video. All processing runs on your machine with open-source models. No paid APIs are required.

Say **"Dictate"** to start (or **"Stop dictation"** to stop), or use the on-screen microphone button. You can also upload audio or video files.

## Features

- **Wake word.** "Dictate" / "Stop dictation" (also 받아쓰기 시작 / 받아쓰기 중지). Uses the browser's speech recognition, or offline Vosk (English "Dictate" / "Stop dictation"). There is a manual microphone button too.
- **Live transcript and translation.** Live text comes from the browser. Each sentence is translated on the server. Audio can be recorded at the same time so **Re-check with Whisper** can redo the text more accurately and add speakers and a summary.
- **Upload any audio or video.** FFmpeg handles MP3, WAV, AAC, M4A, FLAC, OGG, OPUS, WMA, AIFF, AMR, WEBM, MP4, MOV, MKV, AVI, 3GP, CAF, and more, up to 2 GB. Files over 90 MB are uploaded in chunks.
- **Speech-to-text.** [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (`base` / `small` default / `medium`), with timestamps, VAD, and language auto-detect.
- **Translation.** Auto uses Whisper's translate task for any language into English, and [NLLB-200](https://github.com/facebookresearch/fairseq/tree/nllb) distilled 600M (CTranslate2) for other targets. [Argos Translate](https://github.com/argosopentech/argos-translate) is an alternative.
- **Clean transcript.** Paragraphs are built from speaker changes and pauses. Timestamps are optional. Export **.txt, .md, .docx, .srt, .vtt** (original, translation, or both).
- **Speaker labels.** [SpeechBrain](https://github.com/speechbrain/speechbrain) ECAPA embeddings and clustering by default (no token needed). [pyannote](https://github.com/pyannote/pyannote-audio) 3.1 is used automatically if a free Hugging Face token is set in `HF_TOKEN`. Speakers can be renamed in the UI; the rename is applied to exports and the summary.
- **Summary.** [Qwen2.5-1.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct) (int8, CTranslate2) writes the summary and key points. Action items come from the model plus a rule-based extractor. Non-English summaries are translated with NLLB.
- **Read aloud.** [Piper](https://github.com/rhasspy/piper) offline voices (including English and Korean), or the device's built-in voice.
- **Install as an app.** PWA manifest and service worker. On iPhone (Safari): Share → Add to Home Screen. On Mac Safari: File → Add to Dock. On Chrome: install the page as an app. The microphone needs a secure context: `https://` or `http://localhost`.

## Requirements

- macOS (Apple Silicon recommended) or Linux
- Python 3.11 or newer
- [ffmpeg](https://ffmpeg.org/)
- Optional: [cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) for a temporary public HTTPS link (for example, to open the app on a phone)

## Install

```bash
git clone https://github.com/sia14u/dictate.git
cd dictate
./setup.sh
./start.sh
```

`setup.sh` creates a virtualenv and downloads the speech, translation, and summary models. That first run can take several minutes and a few gigabytes of disk.

Then open [http://localhost:8765](http://localhost:8765). `start.sh` also prints a Cloudflare quick-tunnel link if `cloudflared` is installed. Stop the app with `./stop.sh`.

### macOS

```bash
brew install ffmpeg python@3.12 cloudflared
git clone https://github.com/sia14u/dictate.git
cd dictate
./setup.sh
DICTATE_COMPUTE=int8 ./start.sh
```

`DICTATE_COMPUTE=int8` is a good default on Apple Silicon. On some CPUs, CTranslate2 int8 with multiple threads can produce corrupted output; in that case leave the default (`int16`).

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8765` | HTTP port |
| `DICTATE_MODEL` | `small` | Whisper model: `base`, `small`, or `medium` |
| `DICTATE_COMPUTE` | `int16` | CTranslate2 compute type (`int8`, `int16`, or `float32`) |
| `DICTATE_PIN` | unset | Optional access code required for `/api` (not `/api/health`) |
| `HF_TOKEN` | unset | Optional Hugging Face token so speaker labels can use pyannote 3.1. Accept the model terms on Hugging Face first. |
| `NO_TUNNEL` | unset | Set to `1` to skip the Cloudflare quick tunnel |
| `DICTATE_MAX_MB` | `2048` | Maximum upload size in megabytes |

Do not put tokens or PINs in the repository or in chat. Set them in your own shell environment.

## Limits

- The wake word only works **while the page is open and in front** (no background listening in iOS Safari or in installed PWAs). On iPhone, the browser's continuous speech recognition can stop after silence. The app restarts it automatically, but Safari may ask for permission again. The offline Vosk wake word is English-only ("Dictate" / "Stop dictation"). In Vosk mode, the transcript appears after you stop (via Whisper), not live.
- Browser live text in Chrome goes through Google's speech service, and in Safari through Apple's (both free). Choose the Vosk wake word plus Whisper re-check to keep everything local.
- Translation can garble names and slang. Whisper's translate task is usually better when the target is English. A summary from a 1.5B model is a draft, so check numbers and names.
- One job runs at a time; later jobs queue. Files can be up to 2 GB. Jobs and uploads are deleted after 6 hours.
- Cloudflare quick tunnels can be rate-limited. If a public link is not printed, try again later or set `NO_TUNNEL=1` and use `http://localhost:8765`.

## Tests

`python tests/e2e.py` exercises the API against a running server. Sample media is not included in this repository; add your own files under `tests/samples/` or pass a filename that exists there.

## Credits

This app is built on these open-source projects:

- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [NLLB-200](https://github.com/facebookresearch/fairseq/tree/nllb)
- [Argos Translate](https://github.com/argosopentech/argos-translate)
- [Qwen2.5](https://github.com/QwenLM/Qwen2.5)
- [SpeechBrain](https://github.com/speechbrain/speechbrain)
- [pyannote](https://github.com/pyannote/pyannote-audio)
- [Piper](https://github.com/rhasspy/piper)
- [Vosk](https://github.com/alphacep/vosk-api) / [vosk-browser](https://github.com/ccoreilly/vosk-browser)
- [ffmpeg](https://ffmpeg.org/)

Model licenses differ from this project's MIT license. In particular, **NLLB-200 is licensed CC-BY-NC** (Creative Commons Attribution-NonCommercial), so use of that translation model is **non-commercial**. Check each model's license before you use it.

Model choices were also informed by [Voicebox](https://voicebox.sh) ([jamiepine/voicebox](https://github.com/jamiepine/voicebox), MIT).

## License

This repository's source code is released under the [MIT License](LICENSE).
