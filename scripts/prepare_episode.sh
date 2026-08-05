#!/usr/bin/env bash
# Nightly (e.g. 22:00) — make sure tomorrow has an episode.
#
# If one is already queued (you asked for a topic, or dropped source files into
# episodes/NNN/materials/), this only fills in what is missing: audio, translation.
# If nothing is queued, it picks a topic itself using prompts/pick_topic.md and
# prompts/taste.md, then writes and produces it.
#
# It runs the night BEFORE publishing on purpose, so there is a window to read it,
# veto it or edit it before daily_publish.sh ships it in the morning.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

DATE="$(date +%F)"
TOMORROW="$(date -d tomorrow +%F)"
LOG="logs/prepare_${DATE}.log"
STATE=".published"

# cron has a minimal PATH; add the interpreters this needs.
export PATH="$HOME/.local/bin:$HOME/miniconda3/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
[ -n "$NODE_BIN" ] && export PATH="$NODE_BIN:$PATH"

mkdir -p logs
touch "$STATE"

{
  echo "=== PREPARE @ $(date '+%F %H:%M %Z') for ${TOMORROW} ==="
  set -a; source ./config.env; set +a

  # Anything already waiting to go out?
  queued=""
  for d in episodes/*/; do
    slug="$(basename "$d")"
    [ -s "$d/script.txt" ] && [ -f "$d/episode.json" ] || continue
    grep -qxF "$slug" "$STATE" || queued="$slug"
  done

  if [ -n "$queued" ]; then
    echo "Episode $queued is already queued — filling in what is missing."
  else
    next="$(printf '%03d' $(( $(ls -d episodes/*/ 2>/dev/null | wc -l) + 1 )))"
    echo "Nothing queued. Choosing a topic for episode ${next}..."
    claude -p "$(cat prompts/pick_topic.md)"$'\n\nWORKING DIRECTORY: '"${PWD}"$'\nEPISODE NUMBER: '"${next}"$'\nDATE TO USE: '"${TOMORROW}" \
        --allowedTools "Read" "Write" "WebSearch" "WebFetch" \
        --permission-mode acceptEdits \
        >> "$LOG" 2>&1 || { echo "ERROR: topic selection failed — no episode tomorrow."; exit 1; }
    if [ ! -s "episodes/${next}/script.txt" ] || [ ! -f "episodes/${next}/episode.json" ]; then
      echo "ERROR: topic selection produced no usable files."; exit 1
    fi
    python3 -c "import json,sys;json.load(open(sys.argv[1]))" "episodes/${next}/episode.json" \
      || { echo "ERROR: episode.json is not valid JSON."; exit 1; }
    queued="$next"
    echo "Chose: $(python3 -c "import json;print(json.load(open('episodes/${next}/episode.json'))['title'])")"
  fi

  d="episodes/${queued}"

  # A model can produce a plausible-looking URL for a real thing that has no page there.
  # Verify every citation and drop the dead ones BEFORE anything is synthesized.
  echo "Checking citations..."
  python3 scripts/check_links.py "$d" >> "$LOG" 2>&1 \
    || { echo "ERROR: too few usable citations — not shipping this episode."; exit 1; }

  if [ ! -s "$d/audio/podcast-en.m4a" ]; then
    echo "Synthesizing..."
    python3 -c "
import json,sys
s=open(sys.argv[1],encoding='utf-8').read()
json.dump({'podcast':' '.join(s.split())},open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False)
" "$d/script.txt" "$d/narration.json"
    python3 scripts/make_audio.py "$d/narration.json" "$d" >> "$LOG" 2>&1 \
      || { echo "ERROR: TTS failed — not shipping a silent episode."; exit 1; }
  fi

  # Optional second-language transcript, segment-for-segment so the sync survives.
  if [ "${TRANSLATE_TO:-}" != "" ] && [ ! -s "$d/audio/segments_zh.json" ] \
     && [ -s "$d/audio/segments.json" ]; then
    echo "Translating transcript..."
    python3 scripts/translate_segments.py "$d" >> "$LOG" 2>&1 \
      || echo "  translation failed — single language tomorrow"
  fi

  mins="$(python3 -c "import json;print(round(json.load(open('$d/audio/durations.json'))['podcast']/60,1))")"
  echo "=== READY: episode ${queued}, ${mins} min ==="
} >> "$LOG" 2>&1

echo "OK — see $LOG"
tail -n 6 "$LOG"
