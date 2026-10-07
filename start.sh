#!/usr/bin/env bash
# Start Platina: the analysis server, the web page, and (if installed) the
# VOICEVOX tutor voice. Opens your lessons in the browser. Ctrl+C stops it all.

set -u
set -m  # each part in its own process group, so stopping also stops their children
cd "$(dirname "$0")"

API_PORT=${PLATINA_API_PORT:-8000}
WEB_PORT=${PLATINA_WEB_PORT:-5173}
VOICEVOX_PORT=50021
VOICEVOX_RUN=${PLATINA_VOICEVOX_RUN:-$HOME/.local/share/voicevox/linux-cpu-x64/run}
URL="http://localhost:$WEB_PORT/#lessons"
LOGS=${XDG_STATE_HOME:-$HOME/.local/state}/platina
mkdir -p "$LOGS"

in_use() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null || (exec 3<>"/dev/tcp/::1/$1") 2>/dev/null; }

if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then
  echo "Platina isn't installed yet. Follow \"One-time setup\" in LESSONS.md first."
  exit 1
fi
if in_use $API_PORT || in_use $WEB_PORT; then
  echo "Platina already seems to be running (port $API_PORT or $WEB_PORT is in use)."
  echo "Open $URL, or press Ctrl+C in the other terminal first to stop it."
  exit 1
fi

pids=()
stop() {
  trap - INT TERM EXIT
  echo
  echo "Stopping Platina…"
  for p in "${pids[@]}"; do kill -TERM -- "-$p" 2>/dev/null; done
  wait 2>/dev/null
  echo "Stopped."
}
trap stop INT TERM EXIT

(cd backend && exec ../.venv/bin/uvicorn app.main:app --port $API_PORT) > "$LOGS/api.log" 2>&1 &
pids+=($!)
(cd frontend && PLATINA_API_PORT=$API_PORT exec npm run dev -- --port $WEB_PORT --strictPort) > "$LOGS/web.log" 2>&1 &
pids+=($!)
if in_use $VOICEVOX_PORT; then
  echo "Tutor voice: VOICEVOX is already running."
elif [ -x "$VOICEVOX_RUN" ]; then
  "$VOICEVOX_RUN" > "$LOGS/voicevox.log" 2>&1 &
  pids+=($!)
  echo "Tutor voice: starting VOICEVOX."
else
  echo "Tutor voice: VOICEVOX isn't installed, so the ▶ tutor buttons stay off (optional, see LESSONS.md)."
fi

echo -n "Starting Platina"
for _ in $(seq 120); do
  if in_use $API_PORT && in_use $WEB_PORT; then break; fi
  for p in "${pids[@]:0:2}"; do
    if ! kill -0 "$p" 2>/dev/null; then
      echo
      echo "Platina couldn't start. The last lines of its logs ($LOGS):"
      tail -n 15 "$LOGS/api.log" "$LOGS/web.log"
      exit 1
    fi
  done
  echo -n "."
  sleep 1
done
echo
if ! in_use $API_PORT || ! in_use $WEB_PORT; then
  echo "Platina is taking unusually long to start. Logs: $LOGS"
  exit 1
fi

echo "Platina is running: $URL"
echo "Leave this window open while you use it. Press Ctrl+C here to stop."
if [ -z "${PLATINA_NO_BROWSER:-}" ]; then
  if command -v xdg-open > /dev/null; then xdg-open "$URL" > /dev/null 2>&1 &
  elif command -v open > /dev/null; then open "$URL" &  # macOS
  fi
fi
wait "${pids[0]}"
