#!/usr/bin/env bash
# Morning (e.g. 07:00) — rebuild the site and publish it.
#
# It publishes what is READY and invents nothing. An episode counts as ready when its
# folder has episode.json and script.txt; audio is synthesized if prepare_episode.sh
# did not already do it. If there is no new episode, the run rebuilds the same site,
# says so, and exits. A day with no filler is better than a day with filler.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$ROOT"

DATE="$(date +%F)"
LOG="logs/publish_${DATE}.log"
STATE=".published"

export PATH="$HOME/.local/bin:$HOME/miniconda3/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
NODE_BIN="$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | sort -V | tail -1)"
[ -n "$NODE_BIN" ] && export PATH="$NODE_BIN:$PATH"

mkdir -p logs
touch "$STATE"

{
  echo "=== PUBLISH @ $(date '+%F %H:%M %Z') ==="
  set -a; source ./config.env; set +a

  new=0
  for d in episodes/*/; do
    [ -f "$d/episode.json" ] && [ -s "$d/script.txt" ] || continue
    slug="$(basename "$d")"

    if [ ! -s "$d/audio/podcast-en.m4a" ]; then
      echo "Synthesizing $slug ..."
      python3 -c "
import json,sys
s=open(sys.argv[1],encoding='utf-8').read()
json.dump({'podcast':' '.join(s.split())},open(sys.argv[2],'w',encoding='utf-8'),ensure_ascii=False)
" "$d/script.txt" "$d/narration.json"
      python3 scripts/make_audio.py "$d/narration.json" "$d" >> "$LOG" 2>&1 \
        || { echo "  TTS failed for $slug — skipping it this run"; continue; }
    fi

    if [ "${TRANSLATE_TO:-}" != "" ] && [ ! -s "$d/audio/segments_zh.json" ] \
       && [ -s "$d/audio/segments.json" ]; then
      python3 scripts/translate_segments.py "$d" >> "$LOG" 2>&1 \
        || echo "  translation failed for $slug"
    fi

    grep -qxF "$slug" "$STATE" || { echo "New episode ready: $slug"; new=$((new+1)); }
  done

  echo "Rebuilding site..."
  [ "$new" -eq 0 ] && echo "No new episode today — republishing what exists."

  # ---- Delivery target 1: a public web page (HuggingFace static Space) ----------
  # Optional. Set PODCAST_SPACE to enable.
  if [ -n "${PODCAST_SPACE:-}" ]; then
    echo "Building site..."
    python3 scripts/build_site.py site
    # HuggingFace serves static Spaces in 8 KB chunks and mangles UTF-8 characters
    # that straddle a boundary. Must run LAST: it shifts byte offsets.
    python3 scripts/align_utf8.py site/index.html || true
    python3 scripts/publish_hf.py site

    SERVE="https://$(echo "$PODCAST_SPACE" | tr '/' '-').static.hf.space"
    code="$(curl -fsSL -o /dev/null -w '%{http_code}' --max-time 60 "$SERVE/" || echo 000)"
    echo "Site serves HTTP $code"
    [ "$code" = "200" ] || { echo "ERROR: site not serving after publish."; exit 1; }
  fi

  # ---- Delivery target 2: a private podcast feed (Cloudflare Worker + R2) -------
  # Optional. Set RSS_BASE and RSS_UPLOAD_TOKEN to enable.
  # Independent of target 1: either can fail without stopping the other.
  if [ -n "${RSS_BASE:-}" ] && [ -n "${RSS_UPLOAD_TOKEN:-}" ]; then
    echo "Publishing to private RSS feed..."
    UPLOAD_TOKEN="$RSS_UPLOAD_TOKEN" python3 scripts/publish_rss.py \
        --base "$RSS_BASE" --episodes episodes \
        --title "${PODCAST_TITLE:-Daily Podcast}" --author "${PODCAST_AUTHOR:-}" \
        --description "${PODCAST_BLURB:-A private daily podcast.}" \
      && echo "  RSS feed updated" \
      || echo "  WARNING: RSS publish failed"
  fi

  if [ -z "${PODCAST_SPACE:-}" ] && [ -z "${RSS_BASE:-}" ]; then
    echo "ERROR: no delivery target configured. Set PODCAST_SPACE and/or RSS_BASE."
    exit 1
  fi

  for d in episodes/*/; do
    [ -f "$d/episode.json" ] && [ -s "$d/script.txt" ] || continue
    slug="$(basename "$d")"
    grep -qxF "$slug" "$STATE" || echo "$slug" >> "$STATE"
  done

  echo "=== done ($new new episode(s)) ==="
} >> "$LOG" 2>&1

echo "OK — see $LOG"
tail -n 6 "$LOG"
