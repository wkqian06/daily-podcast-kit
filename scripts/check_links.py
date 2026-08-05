#!/usr/bin/env python3
"""Verify an episode's further-reading links actually exist, and drop the ones that don't.

Auto-written episodes are the risk case: a model can produce a plausible-looking URL for a
real thing that has no page at that address. This checks every link and REMOVES dead ones
rather than shipping a citation that 404s.

Bot-blocking is not death: publishers answer curl with 400/402/403 all the time (Nature,
phys.org, Science). Those are kept, with a note in the log. Only a real 404/410, a DNS
failure or a connection error counts as dead.

Usage: check_links.py <episode_dir> [--strict]
  --strict  exit non-zero if anything was dropped (default: only if too few survive)
"""
import json
import os
import sys
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
BLOCKED_BUT_ALIVE = {400, 401, 402, 403, 405, 406, 429}
MIN_SURVIVING = 2


def probe(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, "ok"
    except urllib.error.HTTPError as e:
        if e.code in BLOCKED_BUT_ALIVE:
            return e.code, "blocked"          # exists, just refuses robots
        return e.code, "dead"
    except Exception as e:
        return 0, f"error: {type(e).__name__}"


def main():
    ep_dir = sys.argv[1]
    strict = "--strict" in sys.argv
    path = os.path.join(ep_dir, "episode.json")
    meta = json.load(open(path, encoding="utf-8"))
    items = meta.get("further_reading", [])
    if not items:
        print("check_links: no further_reading to check")
        return 0

    keep, dropped = [], []
    for it in items:
        code, verdict = probe(it["url"])
        mark = {"ok": "OK", "blocked": "BLOCKED(kept)"}.get(verdict, "DEAD")
        print(f"  {code:>3} {mark:<14} {it['url'][:76]}")
        (keep if verdict in ("ok", "blocked") else dropped).append(it)

    if dropped:
        meta["further_reading"] = keep
        json.dump(meta, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"check_links: dropped {len(dropped)} dead link(s):")
        for it in dropped:
            print(f"    - {it['title'][:60]} -> {it['url']}")

    if len(keep) < MIN_SURVIVING:
        print(f"check_links: FAIL — only {len(keep)} usable link(s) left")
        return 1
    if dropped and strict:
        return 1
    print(f"check_links: OK — {len(keep)} link(s) kept")
    return 0


if __name__ == "__main__":
    sys.exit(main())
