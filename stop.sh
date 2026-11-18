#!/usr/bin/env bash
cd "$(dirname "$0")"
for f in tunnel.pid server.pid; do [ -f $f ] && kill "$(cat $f)" 2>/dev/null; rm -f $f; done
pkill -f "cloudflared tunnel --url http://127.0.0.1:${PORT:-8765}" 2>/dev/null
pkill -f "uvicorn server:app --host 127.0.0.1 --port ${PORT:-8765}" 2>/dev/null
for i in $(seq 1 20); do curl -sf "http://127.0.0.1:${PORT:-8765}/api/health" >/dev/null || break; sleep 0.5; done
echo stopped
