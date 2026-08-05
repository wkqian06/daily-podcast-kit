#!/usr/bin/env python3
"""Translate an episode's timed transcript segments into Chinese, one for one.

The transcript is synced to the audio at segment level, so the translation has to keep
the SAME segmentation — then the highlight and click-to-seek keep working in either
language. This translates segment by segment and refuses to write the output unless the
count matches exactly.

Usage: translate_segments.py <episode_dir> [--force]
Reads  <dir>/audio/segments.json, writes <dir>/audio/segments_zh.json
"""
import json
import os
import re
import subprocess
import sys

PROMPT = """Translate this podcast transcript into natural, fluent Chinese (简体).

The input is a JSON array of English segments. Return a JSON array of the SAME LENGTH,
in the SAME ORDER, where element i is the Chinese translation of element i.

Rules:
- One output element per input element. Never merge, split, drop or reorder. The count must match.
- Translate for a technical reader. Keep established English terms and acronyms in English
  where a Chinese reader in the field would expect them: LSTM, VAE, NSE, KGE, AAV, CRISPR,
  base editing, transfer function, leaf area index, and similar. Do not invent Chinese
  neologisms for standard terms.
- Numbers that were spelled out for narration ("zero point seven zero", "thirty two million")
  should become normal Chinese numerals (0.70, 3200 万).
- Keep the register of the original: measured, informed, plain. Do not add emphasis the
  English does not have, and do not soften careful hedging.
- If a segment is a fragment that continues the previous one, translate it as a fragment;
  it will be displayed in sequence.
- Output ONLY the JSON array. No commentary, no code fences.

Write the JSON array to: {out}

Input segments:
{payload}
"""


BATCH = 30


def translate_batch(texts, out_path):
    prompt = PROMPT.format(out=out_path,
                           payload=json.dumps(texts, ensure_ascii=False, indent=1))
    proc = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", "Write", "--permission-mode", "acceptEdits"],
        capture_output=True, text=True, timeout=1800)
    if os.path.exists(out_path):
        try:
            got = json.load(open(out_path, encoding="utf-8"))
            if isinstance(got, list) and len(got) == len(texts):
                return got
        except Exception:
            pass
    # Fall back to whatever it printed, in case it answered instead of writing.
    body = proc.stdout.strip()
    body = re.sub(r"^```(?:json)?|```$", "", body, flags=re.M).strip()
    i, j = body.find("["), body.rfind("]")
    if i != -1 and j > i:
        try:
            got = json.loads(body[i:j + 1])
            if isinstance(got, list) and len(got) == len(texts):
                return got
        except Exception:
            pass
    return None


def main():
    ep_dir = sys.argv[1]
    force = "--force" in sys.argv
    src = os.path.join(ep_dir, "audio", "segments.json")
    dst = os.path.join(ep_dir, "audio", "segments_zh.json")

    if not os.path.exists(src):
        sys.exit(f"no segments.json in {ep_dir}")
    if os.path.exists(dst) and not force:
        print(f"translate_segments: {dst} exists, skipping (use --force)")
        return 0

    segs = json.load(open(src, encoding="utf-8"))
    texts = [s["text"] for s in segs]
    work = os.path.join(ep_dir, "audio", ".zh_batches")
    os.makedirs(work, exist_ok=True)

    out = []
    for b0 in range(0, len(texts), BATCH):
        chunk = texts[b0:b0 + BATCH]
        cache = os.path.join(work, f"b{b0:04d}.json")
        if os.path.exists(cache):          # resume a partial run cheaply
            got = json.load(open(cache, encoding="utf-8"))
            if len(got) == len(chunk):
                out.extend(got)
                print(f"  [{b0}] cached")
                continue
        got = translate_batch(chunk, cache) or translate_batch(chunk, cache)   # one retry
        if got is None:
            sys.exit(f"REFUSING to write: batch at {b0} did not come back aligned "
                     f"({len(chunk)} segments expected)")
        json.dump(got, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
        out.extend(got)
        print(f"  [{b0}] {len(got)} segments")

    if len(out) != len(texts):
        sys.exit(f"REFUSING to write: {len(out)} translations for {len(texts)} segments")

    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"translate_segments: {len(out)} segments -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
