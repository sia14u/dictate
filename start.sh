#!/usr/bin/env bash
# Start Dictate server + public HTTPS tunnel. Usage: ./start.sh   (env: PORT, DICTATE_MODEL, DICTATE_PIN, HF_TOKEN)
cd "$(dirname "$0")"
PORT="${PORT:-8765}"
. .venv/bin/activate
export HF_HUB_DISABLE_TELEMETRY=1 TOKENIZERS_PARALLELISM=false
if ! curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  nohup uvicorn server:app --host 127.0.0.1 --port "$PORT" --timeout-keep-alive 75 > server.log 2>&1 &
  echo $! > server.pid
  for i in $(seq 1 60); do curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && break; sleep 1; done
fi
echo "Local: http://127.0.0.1:$PORT"
if [ "${NO_TUNNEL:-0}" != "1" ]; then
  CF="$(command -v cloudflared || true)"
  if [ -z "$CF" ]; then
    echo "cloudflared not found; skipping tunnel. Install cloudflared or set NO_TUNNEL=1."
  else
    if ! pgrep -f "cloudflared tunnel --url http://127.0.0.1:$PORT" >/dev/null; then
      nohup "$CF" tunnel --no-autoupdate --protocol http2 --url "http://127.0.0.1:$PORT" > tunnel.log 2>&1 &
      echo $! > tunnel.pid
    fi
    for i in $(seq 1 40); do URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' tunnel.log | head -1); [ -n "$URL" ] && break; sleep 1; done
    echo "${URL:-tunnel URL not found yet; see tunnel.log}" | tee public_url.txt
  fi
fi
