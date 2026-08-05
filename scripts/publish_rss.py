#!/usr/bin/env python3
"""Publish episodes to the private feed.

Reads the same episode directories the site build uses, converts the measured
per-sentence timings into WebVTT captions, uploads audio and captions through the
Worker, and replaces the manifest the feed is generated from.

Everything goes through the Worker rather than straight to R2, so there is exactly one
credential to manage and the Worker stays the only thing that knows the bucket layout.

Usage:
  publish.py --base https://your-worker.workers.dev --episodes /path/to/episodes [--dry-run]
Env:
  UPLOAD_TOKEN   bearer token matching the Worker's secret
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

# Cloudflare's bot protection rejects the default Python-urllib User-Agent with a 403
# before the request ever reaches the Worker. Identify as an ordinary client.
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/125.0 Safari/537.36")


def vtt_timestamp(t):
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def segments_to_vtt(segments):
    """The transcript timings are measured during synthesis, not estimated, so these
    captions line up exactly with the audio."""
    out = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        out.append(str(i))
        out.append(f"{vtt_timestamp(seg['start'])} --> {vtt_timestamp(seg['end'])}")
        out.append(seg["text"].strip())
        out.append("")
    return "\n".join(out)


def put(base, token, key, data, content_type, dry=False):
    url = f"{base.rstrip('/')}/upload/{key}"
    if dry:
        print(f"    would PUT {len(data):>9,} B  {content_type:<26} -> {key}")
        return {"ok": True, "bytes": len(data), "dry": True}
    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": f"Bearer {token}", "Content-Type": content_type,
        "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="Worker origin, e.g. https://x.workers.dev")
    ap.add_argument("--episodes", required=True, help="directory of episode folders")
    ap.add_argument("--title", default="The Daily Ten")
    ap.add_argument("--author", default="")
    ap.add_argument("--description", default="A private daily podcast.")
    ap.add_argument("--link", default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("UPLOAD_TOKEN", "")
    if not token and not args.dry_run:
        sys.exit("UPLOAD_TOKEN is not set")

    episodes = []
    for name in sorted(os.listdir(args.episodes)):
        d = os.path.join(args.episodes, name)
        meta_path = os.path.join(d, "episode.json")
        if not os.path.isfile(meta_path):
            continue
        meta = json.load(open(meta_path, encoding="utf-8"))

        audio = next((os.path.join(d, "audio", f"podcast-en{e}")
                      for e in (".m4a", ".mp3")
                      if os.path.exists(os.path.join(d, "audio", f"podcast-en{e}"))), None)
        if not audio:
            print(f"  skip {name}: no audio")
            continue

        num = meta.get("number", 0)
        ext = os.path.splitext(audio)[1]
        audio_key = f"audio/ep{num:03d}{ext}"
        mime = "audio/mp4" if ext == ".m4a" else "audio/mpeg"

        print(f"  ep{num:03d}  {meta['title'][:52]}")
        with open(audio, "rb") as f:
            res = put(args.base, token, audio_key, f.read(), mime, args.dry_run)
        size = res.get("bytes") or os.path.getsize(audio)

        caption_key = None
        seg_path = os.path.join(d, "audio", "segments.json")
        if os.path.exists(seg_path):
            vtt = segments_to_vtt(json.load(open(seg_path, encoding="utf-8")))
            caption_key = f"captions/ep{num:03d}.vtt"
            put(args.base, token, caption_key, vtt.encode("utf-8"), "text/vtt", args.dry_run)

        secs = 0
        dur_path = os.path.join(d, "audio", "durations.json")
        if os.path.exists(dur_path):
            secs = json.load(open(dur_path)).get("podcast", 0)

        episodes.append({
            "number": num,
            "guid": meta.get("slug") or f"ep{num:03d}",
            "title": meta["title"],
            "subtitle": meta.get("subtitle", ""),
            "summary": meta.get("summary", ""),
            "date": meta.get("date", ""),
            "audio_key": audio_key,
            "caption_key": caption_key,
            "bytes": size,
            "seconds": secs,
            "mime": mime,
        })

    manifest = {
        "channel": {
            "title": args.title,
            "author": args.author,
            "description": args.description,
            "link": args.link or args.base,
            "language": "en",
        },
        "episodes": episodes,
    }

    body = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
    if args.dry_run:
        print(f"\n  would POST manifest with {len(episodes)} episode(s)")
    else:
        req = urllib.request.Request(f"{args.base.rstrip('/')}/manifest", data=body,
                                     method="POST",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Content-Type": "application/json",
                                              "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            json.load(r)
        print(f"\n  manifest updated: {len(episodes)} episode(s)")


if __name__ == "__main__":
    main()
