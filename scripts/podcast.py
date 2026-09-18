#!/usr/bin/env python3
"""The whole pipeline except the page template, in one file. Windows and Linux.

    python scripts/podcast.py prepare            nightly: propose 2-3 candidates for tomorrow, then stop
    python scripts/podcast.py prepare --write    write the candidate you confirmed, check its links,
                                                 synthesize, translate. Neither step publishes.
    python scripts/podcast.py publish [--now]    morning: build, publish to every configured target, verify
                                                 (--now: skip the "prepare ran <1 h ago, review first" guard)
    python scripts/podcast.py links     EP_DIR   probe further_reading, drop dead links  [--strict]
    python scripts/podcast.py audio     EP_DIR   Kokoro synthesis -> audio/podcast-en.m4a + segments.json
    python scripts/podcast.py translate EP_DIR   segment-aligned translation -> audio/segments_zh.json  [--force]
    python scripts/podcast.py align     HTML     pad so no UTF-8 char straddles an 8 KB boundary (run LAST)
    python scripts/podcast.py hf        [SITE]   upload the built site to the HuggingFace static Space
    python scripts/podcast.py rss                upload audio + captions to the private feed  [--dry-run]
    python scripts/podcast.py palace    EP_DIR   optionally ingest selected papers into KnowledgePalace
    python scripts/podcast.py weekly              prepare one literature weekly issue and rebuild the site
                                                  [--topic TEXT] [--date YYYY-MM-DD] [--days N] [--draft FILE] [--audio]

Settings come from config.env next to this repo's README (environment variables win).
Every subcommand prints to the console and appends to logs/<command>_<date>.log.
Read LESSONS.md before changing anything here: each odd-looking rule is a bug that shipped.
"""
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPISODES = os.path.join(ROOT, "episodes")
MATERIALS = os.path.join(ROOT, "materials")       # materials/NNN/: papers the listener obtained
WEEKLY_DIR = os.path.join(ROOT, "weekly")
WEEKLY_ISSUES = os.path.join(WEEKLY_DIR, "issues.json")
STATE = os.path.join(ROOT, ".published")          # one slug per line: what has been shipped
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")   # LESSONS §12: the default UA is blocked


def load_config():
    """config.env is KEY="value" lines. Environment variables already set take priority."""
    path = os.path.join(ROOT, "config.env")
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] in ("'", '"'):
            v = v[1:v.find(v[0], 1)] if v.find(v[0], 1) > 0 else v[1:]
        else:
            v = v.split("#")[0].strip()
        os.environ.setdefault(k.strip(), v)


def episode_dirs():
    """The names under episodes/ that are episodes: `NNN`, and nothing else. The repository
    ships `episodes/001-example/` as a format reference — it must never be numbered over,
    narrated or published, and a name that is not a number is the whole test."""
    return sorted(n for n in (os.listdir(EPISODES) if os.path.isdir(EPISODES) else []) if n.isdigit())


def ready_dirs():
    """Episode folders that have both hand-written files. Sorted, so the newest is last."""
    for name in episode_dirs():
        d = os.path.join(EPISODES, name)
        script = os.path.join(d, "script.txt")
        if os.path.isfile(os.path.join(d, "episode.json")) and os.path.isfile(script) \
                and os.path.getsize(script) > 0:
            yield name, d


def published():
    return set(open(STATE, encoding="utf-8").read().split()) if os.path.exists(STATE) else set()


def field(path, name):
    """The value after `NAME:` in a proposal file; empty when the line is blank or absent."""
    for line in open(path, encoding="utf-8"):
        if line.strip().upper().startswith(name + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def claude(prompt, tools, log=None, cwd=None, env=None, add_dirs=()):
    """Run the claude CLI non-interactively. Returns (returncode, stdout).

    The prompt goes in on stdin, never as an argument: Windows caps a whole command line at
    32767 characters, and these prompts carry a file plus the library's gap index. As an argv
    element it dies with `WinError 206` the day the library outgrows the cap. LESSONS §16.
    """
    exe = shutil.which("claude") or "claude"
    cmd = [exe, "-p", "--allowedTools", *tools, "--permission-mode", "acceptEdits"]
    if os.environ.get("CLAUDE_MODEL"):
        cmd += ["--model", os.environ["CLAUDE_MODEL"]]
    if os.environ.get("CLAUDE_EFFORT"):
        cmd += ["--effort", os.environ["CLAUDE_EFFORT"]]
    for d in add_dirs:
        cmd += ["--add-dir", d]
    proc = subprocess.run(cmd, input=prompt, cwd=cwd, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=3600)
    if log:
        log.write(proc.stdout + proc.stderr)
    return proc.returncode, proc.stdout


# ---- links: probe every citation, drop the dead ones (LESSONS §9) ---------------------

BLOCKED_BUT_ALIVE = {400, 401, 402, 403, 405, 406, 429}   # publishers refusing bots, not 404s
MIN_SURVIVING = 2
READ_MARKS = ("Read: full text.", "Read: abstract only.", "Read: not obtained.")  # prompts/write_episode.md


def probe(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, "ok"
    except urllib.error.HTTPError as e:
        return e.code, "blocked" if e.code in BLOCKED_BUT_ALIVE else "dead"
    except Exception as e:
        return 0, f"error: {type(e).__name__}"


def check_links(ep_dir, strict=False):
    """Rewrites episode.json without the dead links. True if enough citations survive."""
    path = os.path.join(ep_dir, "episode.json")
    meta = json.load(open(path, encoding="utf-8"))
    items = meta.get("further_reading", [])
    if not items:
        print("check_links: no further_reading to check")
        return True
    keep, dropped, depths = [], [], []
    for it in items:
        code, verdict = probe(it["url"])
        mark = {"ok": "OK", "blocked": "BLOCKED(kept)"}.get(verdict, "DEAD")
        # A live URL says nothing about whether the writer read the paper. The note has to.
        note = (it.get("note") or "").strip()
        depth = next((m[6:-1] for m in READ_MARKS if note.endswith(m)), "UNDISCLOSED")
        depths.append(depth)
        print(f"  {code:>3} {mark:<14} {depth:<13} {it['url'][:62]}")
        (keep if verdict in ("ok", "blocked") else dropped).append(it)
    undisclosed = depths.count("UNDISCLOSED")
    unread = len(depths) - depths.count("full text") - undisclosed
    if undisclosed:
        print(f"check_links: {undisclosed} note(s) do not say what was read. End each one with "
              + ", ".join(f'"{m}"' for m in READ_MARKS))
    if unread:
        print(f"check_links: {unread} citation(s) were not read in full — read the script against "
              "them before this publishes")
    if dropped:
        meta["further_reading"] = keep
        json.dump(meta, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"check_links: dropped {len(dropped)} dead link(s):")
        for it in dropped:
            print(f"    - {it['title'][:60]} -> {it['url']}")
    if len(keep) < MIN_SURVIVING:
        print(f"check_links: FAIL — only {len(keep)} usable link(s) left")
        return False
    print(f"check_links: OK — {len(keep)} link(s) kept")
    return not ((dropped or undisclosed) and strict)


# ---- audio: Kokoro, sentence by sentence, with measured timings (LESSONS §3, §4) ------

SR = 24000
MAX_CHARS = 140            # well under Kokoro's ~510-phoneme limit, and fine highlight granularity


def split_sentences(text, max_chars):
    parts = re.split(r"(?<=[。！？；!?;])\s*|(?<=[.])\s+", text.strip())
    out, buf = [], ""
    for p in (p for p in parts if p and p.strip()):
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + " " + p) if buf else p
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    return out


def synth(pipeline, text, voice, out_wav):
    """Returns (seconds, segments). Timings are exact because each sentence is its own call."""
    import numpy as np
    import soundfile as sf
    pieces, segments, cursor = [], [], 0.0
    gap = np.zeros(int(SR * 0.28), dtype="float32")      # a breath between sentences
    for sentence in split_sentences(text, MAX_CHARS):
        chunks = [np.asarray(r.audio, dtype="float32") for r in pipeline(sentence, voice=voice)]
        if not chunks:
            continue
        seg = np.concatenate(chunks)
        dur = len(seg) / SR
        segments.append({"start": round(cursor, 2), "end": round(cursor + dur, 2),
                         "text": " ".join(sentence.split())})
        pieces += [seg, gap]
        cursor += dur + len(gap) / SR
    if not pieces:
        raise RuntimeError("synthesis produced no audio")
    audio = np.concatenate(pieces[:-1])                    # drop the trailing gap
    sf.write(out_wav, audio, SR)
    return len(audio) / SR, segments


def encode(wav, stem):
    """32 kbps mono AAC (iOS streams it best) plus MP3 as the universal fallback."""
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    common = ["-y", "-loglevel", "error", "-i", wav, "-ac", "1", "-ar", "24000", "-b:a", "32k"]
    subprocess.run([ff, *common, "-c:a", "aac", "-movflags", "+faststart", stem + ".m4a"], check=True)
    subprocess.run([ff, *common, "-c:a", "libmp3lame", stem + ".mp3"], check=True)
    os.remove(wav)


def pick_device():
    """GPU only if present with headroom; someone else's machine may have neither."""
    if os.environ.get("KOKORO_DEVICE"):
        return os.environ["KOKORO_DEVICE"]
    try:
        import torch
        if torch.cuda.is_available() and torch.cuda.mem_get_info()[0] > 1_500_000_000:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def make_audio(ep_dir):
    """script.txt -> audio/podcast-en.{m4a,mp3}, audio/segments.json, audio/durations.json"""
    import warnings
    warnings.filterwarnings("ignore")
    from kokoro import KPipeline
    text = " ".join(open(os.path.join(ep_dir, "script.txt"), encoding="utf-8").read().split())
    audio_dir = os.path.join(ep_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    voice = os.environ.get("KOKORO_EN_VOICE", "af_heart")
    wav = os.path.join(audio_dir, "podcast-en.wav")
    for device in dict.fromkeys([pick_device(), "cpu"]):    # retry once on CPU if the GPU is full
        print(f"  device: {device}")
        try:
            pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M", device=device)
            secs, segs = synth(pipe, text, voice, wav)
            break
        except RuntimeError as e:
            if device == "cpu" or "out of memory" not in str(e).lower():
                raise
            print("  CUDA out of memory — retrying on CPU")
    json.dump(segs, open(os.path.join(audio_dir, "segments.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump({"podcast": round(secs, 1)},
              open(os.path.join(audio_dir, "durations.json"), "w", encoding="utf-8"))
    encode(wav, os.path.join(audio_dir, "podcast-en"))
    kb = os.path.getsize(os.path.join(audio_dir, "podcast-en.m4a")) / 1024
    print(f"  podcast-en  {secs:.1f}s ({secs/60:.1f} min)  m4a:{kb:.0f}KB  "
          f"expected ~{len(text.split())/150:.1f} min from word count")     # LESSONS §3
    return secs


# ---- translate: per segment, count-checked (LESSONS §5) -------------------------------

TRANSLATE_PROMPT = """Translate this podcast transcript into natural, fluent Chinese (简体).

The input is a JSON array of English segments. Return a JSON array of the SAME LENGTH,
in the SAME ORDER, where element i is the Chinese translation of element i.

Rules:
- One output element per input element. Never merge, split, drop or reorder. The count must match.
- Translate for a technical reader. Keep established English terms and acronyms in English
  where a Chinese reader in the field would expect them: LSTM, VAE, CRISPR, base editing,
  transfer function, and similar. Do not invent Chinese neologisms for standard terms.
- Numbers that were spelled out for narration ("zero point seven zero", "thirty two million")
  should become normal Chinese numerals (0.70, 3200 万).
- Keep the register of the original: measured, informed, plain. Do not add emphasis the
  English does not have, and do not soften careful hedging.
- If a segment is a fragment that continues the previous one, translate it as a fragment.
- Output ONLY the JSON array. No commentary, no code fences.

Write the JSON array to: {out}

Input segments:
{payload}
"""
BATCH = 30


def translate_batch(texts, out_path):
    prompt = TRANSLATE_PROMPT.format(out=out_path, payload=json.dumps(texts, ensure_ascii=False, indent=1))
    _, stdout = claude(prompt, ["Write"])
    candidates = []
    if os.path.exists(out_path):
        candidates.append(open(out_path, encoding="utf-8").read())
    body = re.sub(r"^```(?:json)?|```$", "", stdout.strip(), flags=re.M).strip()
    i, j = body.find("["), body.rfind("]")
    if i != -1 and j > i:
        candidates.append(body[i:j + 1])          # it answered instead of writing the file
    for c in candidates:
        try:
            got = json.loads(c)
            if isinstance(got, list) and len(got) == len(texts):
                return got
        except Exception:
            pass
    return None


def translate(ep_dir, force=False):
    src = os.path.join(ep_dir, "audio", "segments.json")
    dst = os.path.join(ep_dir, "audio", "segments_zh.json")
    if not os.path.exists(src):
        sys.exit(f"no segments.json in {ep_dir}")
    if os.path.exists(dst) and not force:
        print(f"translate: {dst} exists, skipping (use --force)")
        return
    texts = [s["text"] for s in json.load(open(src, encoding="utf-8"))]
    work = os.path.join(ep_dir, "audio", ".zh_batches")     # per-batch cache: a failed run resumes cheaply
    os.makedirs(work, exist_ok=True)
    out = []
    for b0 in range(0, len(texts), BATCH):
        chunk = texts[b0:b0 + BATCH]
        cache = os.path.join(work, f"b{b0:04d}.json")
        if os.path.exists(cache):
            got = json.load(open(cache, encoding="utf-8"))
            if len(got) == len(chunk):
                out.extend(got)
                print(f"  [{b0}] cached")
                continue
        got = translate_batch(chunk, cache) or translate_batch(chunk, cache)   # one retry
        if got is None:
            sys.exit(f"REFUSING to write: batch at {b0} did not come back aligned ({len(chunk)} expected)")
        json.dump(got, open(cache, "w", encoding="utf-8"), ensure_ascii=False)
        out.extend(got)
        print(f"  [{b0}] {len(got)} segments")
    if len(out) != len(texts):
        sys.exit(f"REFUSING to write: {len(out)} translations for {len(texts)} segments")
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"translate: {len(out)} segments -> {dst}")


# ---- align: HuggingFace mangles UTF-8 on 8 KB boundaries (LESSONS §2). Run LAST. --------

CHUNK = 8192


def straddles(data):
    """First chunk boundary that lands inside a multi-byte character, or None."""
    for pos in range(CHUNK, len(data), CHUNK):
        if 0x80 <= data[pos] <= 0xBF:
            return pos
    return None


def align_utf8(path):
    data = open(path, "rb").read()
    inserted = 0
    while (pos := straddles(data)) is not None and inserted < 400:
        j = data.rfind(b"><", 0, pos)             # whitespace between tags is inert
        if j == -1:
            j = data.rfind(b">", 0, pos)
        if j == -1:
            break
        data = data[:j + 1] + b" " + data[j + 1:]
        inserted += 1
    if inserted:
        open(path, "wb").write(data)
    left = straddles(data)
    print(f"align_utf8: {inserted} pad byte(s) inserted, "
          f"{'clean' if left is None else f'STILL STRADDLING at {left}'} — {path}")
    return left is None


# ---- weekly: prepare a literature issue owned by the podcast project -----------------

def parse_weekly_args(argv):
    import argparse
    parser = argparse.ArgumentParser(prog="podcast.py weekly")
    parser.add_argument("--topic", default="the listener's current research interests")
    parser.add_argument("--date", default=str(datetime.date.today()))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--draft", help="install an existing issue JSON without calling Claude")
    parser.add_argument("--audio", action="store_true", help="synthesise the draft script as weekly audio")
    parser.add_argument("--skip-links", action="store_true", help="skip URL probes when working offline")
    return parser.parse_args(argv)


def extract_json(stdout):
    body = stdout.strip()
    start, end = body.find("{"), body.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        value = json.loads(body[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def validate_weekly_issue(issue, expected_id, expected_number):
    errors = []
    required = ("id", "number", "date", "window", "title", "subtitle", "thread", "note",
                "topics", "papers", "progress", "briefs", "audio")
    errors.extend("missing weekly field: " + key for key in required if key not in issue)
    if issue.get("id") != expected_id:
        errors.append("weekly issue id must be " + expected_id)
    if issue.get("date") != expected_id:
        errors.append("weekly issue date must match its id")
    if issue.get("number") != expected_number:
        errors.append("weekly issue number must be %d" % expected_number)
    if not isinstance(issue.get("papers"), list) or not issue.get("papers"):
        errors.append("weekly issue needs at least one paper")
    if not isinstance(issue.get("topics"), dict):
        errors.append("weekly topics must be an object")
    if not isinstance(issue.get("briefs"), list):
        errors.append("weekly briefs must be an array")
    for number, brief in enumerate(issue.get("briefs") or [], 1):
        for key in ("title", "category", "text", "url"):
            if key not in brief:
                errors.append("brief %d missing %s" % (number, key))
        url = brief.get("url", "")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            errors.append("brief %d URL must be http(s)" % number)
    for number, paper in enumerate(issue.get("papers") or [], 1):
        for key in ("title", "url", "tags", "summary", "findings", "limits", "evidence",
                    "source_coverage", "read_depth"):
            if key not in paper:
                errors.append("paper %d missing %s" % (number, key))
        if paper.get("source_coverage") not in ("full-text", "excerpt", "abstract", "metadata"):
            errors.append("paper %d has invalid source_coverage" % number)
        if paper.get("read_depth") not in ("full", "skim", "abstract", "metadata"):
            errors.append("paper %d has invalid read_depth" % number)
        if paper.get("source_coverage") in ("abstract", "metadata") and paper.get("read_depth") in ("full", "skim"):
            errors.append("paper %d labels limited material as full/skim reading" % number)
        if not isinstance(paper.get("tags"), list) or any(tag not in issue.get("topics", {}) for tag in paper.get("tags", [])):
            errors.append("paper %d uses an undeclared topic" % number)
        url = paper.get("url", "")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            errors.append("paper %d URL must be http(s)" % number)
    return errors


def install_weekly_issue(issue, draft_path, opts, log):
    os.makedirs(WEEKLY_DIR, exist_ok=True)
    existing = json.load(open(WEEKLY_ISSUES, encoding="utf-8")) if os.path.exists(WEEKLY_ISSUES) else []
    if not isinstance(existing, list):
        raise ValueError("weekly/issues.json must contain an array")
    expected_number = max((item.get("number", 0) for item in existing), default=0) + 1
    expected_id = opts.date
    errors = validate_weekly_issue(issue, expected_id, expected_number)
    if any(item.get("id") == expected_id for item in existing):
        errors.append("weekly issue already exists: " + str(expected_id))
    if not opts.skip_links:
        for url in [item.get("url") for item in issue.get("papers", []) + issue.get("briefs", [])
                    if item.get("url")]:
            code, verdict = probe(url)
            if verdict == "dead":
                errors.append("dead weekly URL (%d): %s" % (code, url))
    if errors:
        raise ValueError("weekly issue not installed: " + "; ".join(errors))
    if os.environ.get("PALACE_DIR"):
        selected = (issue.get("palace") or {}).get("ingest") or []       # same key as episode.json
        issue.setdefault("provenance", {})["knowledge_palace_ingest"] = \
            palace_ingest(selected, log) if selected else {"status": "none", "saved": []}
    try:
        draft_ref = os.path.relpath(draft_path, ROOT)
    except ValueError:
        draft_ref = os.path.abspath(draft_path)
    issue.setdefault("provenance", {})["draft"] = draft_ref.replace(os.sep, "/")
    issue["provenance"]["owner"] = "daily-podcast-kit"
    if opts.audio:
        draft_dir = os.path.dirname(draft_path)
        script = os.path.join(draft_dir, "script.txt")
        if not os.path.isfile(script):
            raise ValueError("--audio requires script.txt beside the draft JSON")
        make_audio(draft_dir)
        target_dir = os.path.join(WEEKLY_DIR, "audio")
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, issue["id"] + ".m4a")
        shutil.copyfile(os.path.join(draft_dir, "audio", "podcast-en.m4a"), target)
        issue.setdefault("audio", []).append({
            "title": {"zh": "本期完整周报", "en": "Full weekly report"},
            "note": {"zh": "podcast 项目合成语音", "en": "Synthesized by the podcast project"},
            "url": "audio/" + issue["id"] + ".m4a",
        })
    existing.insert(0, issue)
    with open(WEEKLY_ISSUES, "w", encoding="utf-8") as stream:
        json.dump(existing, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    sys.path.insert(0, HERE)
    import build_site
    build_site.build("site")
    align_utf8(os.path.join("site", "index.html"))
    align_utf8(os.path.join("site", "weekly", "index.html"))
    print("weekly: installed %s with %d paper(s) -> site/weekly/index.html" %
          (issue["id"], len(issue["papers"])))


def prepare_weekly(argv, log):
    opts = parse_weekly_args(argv)
    try:
        end = datetime.date.fromisoformat(opts.date)
    except ValueError as exc:
        raise SystemExit("weekly --date must be YYYY-MM-DD") from exc
    if opts.days < 1:
        raise SystemExit("weekly --days must be positive")
    start = end - datetime.timedelta(days=opts.days - 1)
    draft_path = opts.draft or os.path.join(WEEKLY_DIR, "drafts", end.isoformat(), "issue.json")
    draft_path = os.path.abspath(draft_path)
    os.makedirs(os.path.dirname(draft_path), exist_ok=True)
    stdout = ""
    if not opts.draft:
        existing = json.load(open(WEEKLY_ISSUES, encoding="utf-8")) if os.path.exists(WEEKLY_ISSUES) else []
        next_number = max((item.get("number", 0) for item in existing), default=0) + 1
        # The editorial rules and the JSON contract live in prompts/weekly.md; only the facts of
        # this run are appended here, the same way prepare appends to prompts/propose_topic.md.
        prompt = (open("prompts/weekly.md", encoding="utf-8").read()
                  + f"\n\nWORKING DIRECTORY: {ROOT}\nISSUE NUMBER: {next_number}\n"
                    f"ISSUE DATE (also its id): {end}\nREADING WINDOW: {start} through {end}\n"
                    f"TOPIC: {opts.topic}\nDRAFT JSON PATH: {draft_path}\n"
                  + (f"NARRATION: also write an English narration to "
                     f"{os.path.join(os.path.dirname(draft_path), 'script.txt')}\n" if opts.audio else
                     "NARRATION: none; do not create audio\n"))
        rc, stdout = write_run(prompt, log)
        if rc != 0:
            raise SystemExit("weekly: Claude did not complete the draft")
    if os.path.isfile(draft_path):
        issue = json.load(open(draft_path, encoding="utf-8"))
    else:
        issue = extract_json(stdout)
        if issue is None:
            raise SystemExit("weekly: no issue JSON was written")
        with open(draft_path, "w", encoding="utf-8") as stream:
            json.dump(issue, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    install_weekly_issue(issue, draft_path, opts, log)


# ---- hf: one static Space for the whole series --------------------------------------

def publish_hf(site_dir):
    from huggingface_hub import HfApi
    token, repo = os.environ["HF_TOKEN"], os.environ["PODCAST_SPACE"]
    api = HfApi(token=token)
    readme = f"""---
title: {os.environ.get("PODCAST_TITLE", "Daily Podcast")}
emoji: 🎙
colorFrom: indigo
colorTo: blue
sdk: static
pinned: false
---

A daily ten-minute podcast. Every episode has a synced transcript, comprehension
questions and links to its sources.
Use the **Community** tab to request a topic — feedback shapes what gets made next.
"""
    # static, not gradio/docker: those need a PRO account and fail with 402
    api.create_repo(repo, repo_type="space", space_sdk="static", exist_ok=True)
    api.upload_file(path_or_fileobj=readme.encode("utf-8"), path_in_repo="README.md",
                    repo_id=repo, repo_type="space")
    api.upload_folder(folder_path=site_dir, repo_id=repo, repo_type="space",
                      commit_message="Publish site")
    owner, name = repo.split("/")
    print(f"SITE_URL=https://huggingface.co/spaces/{repo}")
    print(f"SERVE_URL=https://{owner}-{name}.static.hf.space")
    print(f"DISCUSS_URL=https://huggingface.co/spaces/{repo}/discussions")
    return f"https://{owner}-{name}.static.hf.space"


# ---- rss: audio + WebVTT captions through the Worker, then the manifest ----------------

def vtt_timestamp(t):
    return f"{int(t // 3600):02d}:{int(t % 3600 // 60):02d}:{t % 60:06.3f}"


def segments_to_vtt(segments):
    out = ["WEBVTT", ""]
    for i, seg in enumerate(segments, 1):
        out += [str(i), f"{vtt_timestamp(seg['start'])} --> {vtt_timestamp(seg['end'])}",
                seg["text"].strip(), ""]
    return "\n".join(out)


def put(base, token, key, data, content_type, dry=False):
    if dry:
        print(f"    would PUT {len(data):>9,} B  {content_type:<26} -> {key}")
        return {"ok": True, "bytes": len(data)}
    req = urllib.request.Request(f"{base.rstrip('/')}/upload/{key}", data=data, method="PUT",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": content_type, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def publish_rss(dry=False):
    base, token = os.environ["RSS_BASE"], os.environ.get("RSS_UPLOAD_TOKEN", "")
    if not token and not dry:
        sys.exit("RSS_UPLOAD_TOKEN is not set")
    episodes = []
    for name, d in ready_dirs():
        meta = json.load(open(os.path.join(d, "episode.json"), encoding="utf-8"))
        audio = next((os.path.join(d, "audio", f"podcast-en{e}") for e in (".m4a", ".mp3")
                      if os.path.exists(os.path.join(d, "audio", f"podcast-en{e}"))), None)
        if not audio:
            print(f"  skip {name}: no audio")
            continue
        num, ext = meta.get("number", 0), os.path.splitext(audio)[1]
        audio_key, mime = f"audio/ep{num:03d}{ext}", "audio/mp4" if ext == ".m4a" else "audio/mpeg"
        print(f"  ep{num:03d}  {meta['title'][:52]}")
        res = put(base, token, audio_key, open(audio, "rb").read(), mime, dry)
        caption_key, seg_path = None, os.path.join(d, "audio", "segments.json")
        if os.path.exists(seg_path):
            caption_key = f"captions/ep{num:03d}.vtt"
            vtt = segments_to_vtt(json.load(open(seg_path, encoding="utf-8")))
            put(base, token, caption_key, vtt.encode("utf-8"), "text/vtt", dry)
        dur_path = os.path.join(d, "audio", "durations.json")
        secs = json.load(open(dur_path, encoding="utf-8")).get("podcast", 0) if os.path.exists(dur_path) else 0
        episodes.append({"number": num, "guid": meta.get("slug") or f"ep{num:03d}",
                         "title": meta["title"], "subtitle": meta.get("subtitle", ""),
                         "summary": meta.get("summary", ""), "date": meta.get("date", ""),
                         "audio_key": audio_key, "caption_key": caption_key,
                         "bytes": res.get("bytes") or os.path.getsize(audio),
                         "seconds": secs, "mime": mime})
    manifest = {"channel": {"title": os.environ.get("PODCAST_TITLE", "Daily Podcast"),
                            "author": os.environ.get("PODCAST_AUTHOR", ""),
                            "description": os.environ.get("PODCAST_BLURB", "A private daily podcast."),
                            "link": base, "language": "en"},
                "episodes": episodes}
    body = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
    if dry:
        print(f"\n  would POST manifest with {len(episodes)} episode(s)")
        return
    req = urllib.request.Request(f"{base.rstrip('/')}/manifest", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        json.load(r)
    print(f"\n  manifest updated: {len(episodes)} episode(s)")


# ---- palace: optional KnowledgePalace literature interface (docs/PALACE.md) ------------

QUEUE = os.path.join(ROOT, "prompts", "queue.md")   # the listener's topics, one per line, consumed top-down
INGEST_PROMPT = """Ingest the papers listed below into the library. Follow CLAUDE.md and
knowledge_palace/workflows/ingest.md in this directory.

Standing authorization: the user has pre-approved ingesting the papers explicitly listed below
when they fall inside a registered domain. There is no interactive user: do not ask for
confirmation and do not stop to present a selection. Write the cards.

For each paper:
- Resolve its identity (DOI, arXiv id, title) against the existing papers. Reuse an existing slug
  and deepen that card instead of creating a duplicate.
- Acquire the best available source (open-access PDF, arXiv, publisher HTML) through the existing
  providers or WebFetch and store it in the Source Cache. Record the honest source_coverage and
  read_depth. An abstract-only card says so and contains no invented full-text findings.
- Tag `domain:` only with registered slugs from domains.md. A paper that turns out to fall outside
  every registered domain is skipped.
- Save through acquisition.transaction.save_paper. After the whole batch run
  graph.builder.ensure_index once.
- Treat the caller only as an external ingest interface. Do not create a project, material record,
  episode record or report in KnowledgePalace, and do not mention the caller in paper cards,
  concepts, gaps or acquisition provenance.

When done, print exactly one line `PALACE_INGEST_OK <space-separated slugs saved>` (the slugs may be
empty), then one line `PALACE_INGEST_SKIP <id> <reason>` per skipped paper.

Papers:
{items}
"""


def palace():
    """(framework dir, {root: Path}) from PALACE_DIR. Also makes knowledge_palace importable."""
    p = os.path.abspath(os.path.join(ROOT, os.environ["PALACE_DIR"]))
    if p not in sys.path:
        sys.path.insert(0, p)
    from knowledge_palace.tools.config_resolver import resolve_roots
    return p, resolve_roots(os.path.join(p, ".palace.toml"))


def palace_header(with_gaps):
    """Appended to the nightly prompt: how to query the library, its domains, and (when the listener
    named no topic) its open gaps to choose from."""
    p, roots = palace()
    vault = str(roots["vault_dir"])
    text = (f"\n\nPALACE: yes\nPALACE_CONFIG: {os.path.join(p, '.palace.toml')}\nPALACE_VAULT: {vault}\n\n"
            "REGISTERED DOMAINS (domains.md):\n"
            + open(os.path.join(vault, "domains.md"), encoding="utf-8").read())
    if with_gaps:
        text += ("\n\nOPEN GAPS (gaps/INDEX.md) — choose the topic from these:\n"
                 + open(os.path.join(vault, "gaps", "INDEX.md"), encoding="utf-8").read())
    return text


def palace_tools():
    """(extra allowed tools, env, add_dirs) that let a writing agent query the library read-only."""
    p, roots = palace()
    return (["Bash(python -m knowledge_palace.interaction.research:*)",        # Windows may offer
             "PowerShell(python -m knowledge_palace.interaction.research:*)"],  # either shell
            {**os.environ, "PYTHONPATH": p, "PYTHONUTF8": "1"},
            [str(roots["vault_dir"])])                         # Read paper cards for bibliographic data


def write_run(prompt, log, with_gaps=False):
    """The three writing runs — propose, write, weekly — differ only in their prompt. Each gets
    read-only library access appended when PALACE_DIR is set, and nothing when it is not."""
    tools, env, dirs = ["Read", "Write", "WebSearch", "WebFetch"], None, ()
    if os.environ.get("PALACE_DIR"):                     # docs/PALACE.md
        prompt += palace_header(with_gaps)
        extra, env, dirs = palace_tools()
        tools += extra
    return claude(prompt, tools, log, env=env, add_dirs=dirs)


def palace_ingest(selected, log):
    """Run the library's own ingest workflow, inside PALACE_DIR, on the selected papers.
    Returns the receipt the caller stores in its own records."""
    p, roots = palace()
    items = "\n".join(f'- {i.get("title", "")} | {i.get("id", "")} | domain: {i.get("domain", "?")}'
                      for i in selected)
    rc, out = claude(INGEST_PROMPT.format(items=items),
                     ["Read", "Write", "Edit", "Glob", "Grep", "WebFetch", "WebSearch",
                      "Bash(python:*)", "PowerShell(python:*)"],
                     log, cwd=p, env={**os.environ, "PYTHONUTF8": "1"},
                     add_dirs=[str(r) for r in roots.values()])
    match = re.search(r"^PALACE_INGEST_OK(.*)$", out, re.M)
    if rc != 0 or not match:
        raise RuntimeError("KnowledgePalace ingest did not complete; see the log")
    return {"status": "ok", "completed": str(datetime.date.today()), "saved": match.group(1).split(),
            "skipped": re.findall(r"^PALACE_INGEST_SKIP\s+(.+)$", out, re.M)}


def palace_ingest_episode(ep_dir, log):
    """Optionally ingest an episode's selected papers; the receipt stays in its episode.json."""
    meta_path = os.path.join(ep_dir, "episode.json")
    meta = json.load(open(meta_path, encoding="utf-8"))
    selected = (meta.get("palace") or {}).get("ingest") or []
    if (meta.get("knowledge_palace_ingest") or {}).get("status") == "ok":
        print("  palace: selected papers were already ingested; receipt remains in episode.json")
    elif not selected:
        print("  palace: no papers selected for optional ingest")
    else:
        print(f"  palace: ingesting {len(selected)} selected paper(s)...")
        meta["knowledge_palace_ingest"] = palace_ingest(selected, log)
        with open(meta_path, "w", encoding="utf-8") as stream:
            json.dump(meta, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"  palace: ingested {', '.join(meta['knowledge_palace_ingest']['saved']) or 'nothing'}; "
              "receipt saved in episode.json")


# =====================================================================================

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd not in ("prepare", "publish", "links", "audio", "translate", "align", "hf", "rss", "palace", "weekly"):
        sys.exit(__doc__)
    os.chdir(ROOT)
    load_config()
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")     # Windows without dev mode
    today = datetime.date.today()

    # ---- console + logs/<cmd>_<date>.log, both UTF-8 (a cp936 console would crash on 🎙) ----
    os.makedirs("logs", exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    log = open(os.path.join("logs", f"{cmd}_{today}.log"), "a", encoding="utf-8")
    console = sys.stdout

    class Tee:
        def write(self, s):
            console.write(s); log.write(s); console.flush(); log.flush()
        def flush(self):
            console.flush(); log.flush()
        def isatty(self): return False      # huggingface_hub upload_folder calls sys.stderr.isatty()
    sys.stdout = sys.stderr = Tee()
    print(f"=== {cmd.upper()} @ {datetime.datetime.now():%F %H:%M} ===")

    # ---- single steps, for adding an episode by hand ---------------------------------
    if cmd == "links":
        sys.exit(0 if check_links(sys.argv[2], "--strict" in sys.argv) else 1)
    elif cmd == "audio":
        make_audio(sys.argv[2])
    elif cmd == "translate":
        translate(sys.argv[2], "--force" in sys.argv)
    elif cmd == "align":
        sys.exit(0 if align_utf8(sys.argv[2]) else 1)
    elif cmd == "hf":
        publish_hf(sys.argv[2] if len(sys.argv) > 2 else "site")
    elif cmd == "rss":
        publish_rss("--dry-run" in sys.argv)
    elif cmd == "weekly":
        prepare_weekly(sys.argv[2:], log)
    elif cmd == "palace":
        palace_ingest_episode(sys.argv[2], log)

    # ---- nightly: propose tomorrow's topic and stop. --write turns the candidate the listener
    # ---- confirmed into an episode. Neither step publishes anything (LESSONS §10) ----
    elif cmd == "prepare":
        tomorrow = today + datetime.timedelta(days=1)
        write = "--write" in sys.argv
        queued = [n for n, _ in ready_dirs() if n not in published()]
        # A proposal directory holds topic.md and no script until the listener picks a candidate.
        waiting = [n for n in episode_dirs()
                   if os.path.isfile(os.path.join(EPISODES, n, "topic.md"))
                   and not os.path.isfile(os.path.join(EPISODES, n, "script.txt"))]

        if queued:                   # the listener wrote this one themselves: just finish production
            slug = queued[-1]
            print(f"Episode {slug} is already written — filling in what is missing.")

        elif not waiting:            # ---- propose: candidates only, no narration exists yet ------
            if write:
                sys.exit("ERROR: nothing to write — run `prepare` first, then confirm a candidate.")
            # Topic source, in order: the listener's queue, then the library's open questions.
            # There is no third source: a night with neither ends here rather than inventing one.
            queue = open(QUEUE, encoding="utf-8").read().splitlines() if os.path.exists(QUEUE) else []
            topic = next((l.strip() for l in queue if l.strip() and not l.startswith("#")), "")
            if not topic and not os.environ.get("PALACE_DIR"):
                sys.exit("Nothing queued and no library configured — no proposal tonight.")
            slug = f"{len(episode_dirs()) + 1:03d}"
            topic_md = os.path.join(EPISODES, slug, "topic.md")
            os.makedirs(os.path.dirname(topic_md), exist_ok=True)
            print(f"Episode {slug}: " + (f"angles on the listener's topic: {topic}" if topic
                                         else "candidates from the library's open questions..."))
            prompt = (open("prompts/propose_topic.md", encoding="utf-8").read()
                      + f"\n\nWORKING DIRECTORY: {ROOT}\nEPISODE NUMBER: {slug}\nDATE TO USE: {tomorrow}"
                        f"\nTOPIC FILE: {topic_md}"
                      + (f"\nTOPIC (from the listener): {topic}" if topic else ""))
            rc, _ = write_run(prompt, log, with_gaps=not topic)
            if rc != 0 or not os.path.isfile(topic_md):
                sys.exit("ERROR: no proposal written — nothing to confirm.")
            # Where it came from is known here and nowhere else; --write reads these back.
            with open(topic_md, "a", encoding="utf-8") as f:
                f.write(f"\nSOURCE: {'listener' if topic else 'library'}\n"
                        + (f"QUEUE: {topic}\n" if topic else ""))
            print(open(topic_md, encoding="utf-8").read())
            print(f"=== PROPOSED: episode {slug}. Write your pick after CHOICE: in {topic_md}, put "
                  f"any paper I could not reach into materials/{slug}/, then run:\n"
                  f"    python scripts/podcast.py prepare --write ===")
            sys.exit(0)

        else:                        # ---- a proposal is on the table ---------------------------
            slug = waiting[0]
            d = os.path.join(EPISODES, slug)
            topic_md = os.path.join(d, "topic.md")
            choice = field(topic_md, "CHOICE")
            if not write:            # the nightly job never writes: confirming is the listener's step
                print(open(topic_md, encoding="utf-8").read())
                print(f"=== WAITING: episode {slug} is proposed and not confirmed. Fill in CHOICE: "
                      f"and run `prepare --write`, or delete episodes/{slug}/ to be offered "
                      f"something else. ===")
                sys.exit(0)
            if not choice:
                sys.exit(f"ERROR: the CHOICE line in {topic_md} is empty — pick a candidate first.")
            mats = os.path.join(MATERIALS, slug)
            materials = sorted(os.listdir(mats)) if os.path.isdir(mats) else []
            print(f"Writing episode {slug}: {choice}")
            prompt = (open("prompts/write_episode.md", encoding="utf-8").read()
                      + f"\n\nWORKING DIRECTORY: {ROOT}\nEPISODE DIRECTORY: episodes/{slug}"
                        f"\nEPISODE NUMBER: {slug}\nDATE TO USE: {tomorrow}"
                        f"\nCHOSEN TOPIC: {choice}\nPROPOSAL FILE: {topic_md}"
                      + ("\nMATERIALS (the listener obtained these because you could not):\n"
                         + "\n".join(f"  - materials/{slug}/{f}" for f in materials)
                         if materials else ""))
            rc, _ = write_run(prompt, log)
            if rc != 0 or not os.path.exists(os.path.join(d, "script.txt")) \
                    or not os.path.exists(os.path.join(d, "episode.json")):
                sys.exit("ERROR: writing produced no usable files — no episode tomorrow.")
            meta = json.load(open(os.path.join(d, "episode.json"), encoding="utf-8"))
            print(f"Wrote: {meta['title']}")
            # Topic provenance remains podcast metadata; it does not create a library project.
            meta["topic_source"] = field(topic_md, "SOURCE") or "listener"
            json.dump(meta, open(os.path.join(d, "episode.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            consumed = field(topic_md, "QUEUE")   # consumed now, so a vetoed proposal keeps it queued
            if consumed and os.path.exists(QUEUE):
                queue = open(QUEUE, encoding="utf-8").read().splitlines()
                if consumed in [l.strip() for l in queue]:
                    del queue[[l.strip() for l in queue].index(consumed)]
                    open(QUEUE, "w", encoding="utf-8").write("\n".join(queue) + "\n")

        d = os.path.join(EPISODES, slug)

        print("Checking citations...")                    # BEFORE synthesis: a model invents URLs
        if not check_links(d):
            sys.exit("ERROR: too few usable citations — not shipping this episode.")
        if not os.path.exists(os.path.join(d, "audio", "podcast-en.m4a")):
            print("Synthesizing...")
            try:
                make_audio(d)
            except Exception as e:
                sys.exit(f"ERROR: TTS failed ({e}) — not shipping a silent episode.")
        if os.environ.get("TRANSLATE_TO") and not os.path.exists(os.path.join(d, "audio", "segments_zh.json")):
            print("Translating transcript...")
            try:
                translate(d)
            except SystemExit as e:
                print(f"  translation failed — single language tomorrow ({e})")
        secs = json.load(open(os.path.join(d, "audio", "durations.json"), encoding="utf-8"))["podcast"]
        print(f"=== READY: episode {slug}, {secs/60:.1f} min ===")

    # ---- morning: build and publish what is ready; invent nothing ---------------------
    elif cmd == "publish":
        space, rss = os.environ.get("PODCAST_SPACE"), os.environ.get("RSS_BASE")
        if not space and not rss:
            sys.exit("ERROR: no delivery target configured. Set PODCAST_SPACE and/or RSS_BASE.")
        # A scheduler that was asleep overnight fires both jobs back to back at wake-up. That
        # would ship an episode nobody read. Refuse if prepare finished less than an hour ago.
        prep_log = os.path.join("logs", f"prepare_{today}.log")
        if "--now" not in sys.argv and os.path.exists(prep_log) \
                and datetime.datetime.now().timestamp() - os.path.getmtime(prep_log) < 3600:
            sys.exit("ERROR: prepare ran less than an hour ago — review the episode first, "
                     "then run `publish --now`.")
        done, new = published(), []
        for slug, d in ready_dirs():
            if not os.path.exists(os.path.join(d, "audio", "podcast-en.m4a")):
                print(f"Synthesizing {slug} ...")
                try:
                    make_audio(d)
                except Exception as e:
                    print(f"  TTS failed for {slug} ({e}) — skipping it this run")
                    continue
            if os.environ.get("TRANSLATE_TO") and not os.path.exists(os.path.join(d, "audio", "segments_zh.json")):
                try:
                    translate(d)
                except SystemExit as e:
                    print(f"  translation failed for {slug} ({e})")
            if slug not in done:
                print(f"New episode ready: {slug}")
                new.append(slug)
                # Dated the day it goes out: prepare's "tomorrow" is wrong once prepare slips past
                # midnight or the episode is published the same day.
                ep_json = os.path.join(d, "episode.json")
                meta = json.load(open(ep_json, encoding="utf-8"))
                meta["date"] = str(today)
                json.dump(meta, open(ep_json, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        if not new:
            print("No new episode today — republishing what exists.")

        failed = []
        if space:
            print("Building site...")
            sys.path.insert(0, HERE)
            import build_site
            build_site.build("site")
            align_utf8(os.path.join("site", "index.html"))        # must be the last edit to the HTML
            if os.path.exists(os.path.join("site", "weekly", "index.html")):
                align_utf8(os.path.join("site", "weekly", "index.html"))
            try:
                serve = publish_hf("site")
                for attempt in range(6):                  # a fresh Space takes up to a minute to serve
                    try:
                        with urllib.request.urlopen(urllib.request.Request(serve + "/", headers={"User-Agent": UA}),
                                                    timeout=60) as r:
                            print(f"Site serves HTTP {r.status}")
                        break
                    except Exception:
                        if attempt == 5:
                            raise
                        time.sleep(15)
            except Exception as e:
                print(f"ERROR: web page publish failed: {e}")
                failed.append("web")
        if rss:
            print("Publishing to private RSS feed...")
            try:
                publish_rss()
            except Exception as e:
                print(f"WARNING: RSS publish failed: {e}")
                failed.append("rss")
        if len(failed) == (bool(space) + bool(rss)):
            sys.exit("ERROR: every delivery target failed — nothing marked as published.")
        with open(STATE, "a", encoding="utf-8") as f:
            for slug in new:
                f.write(slug + "\n")
        if os.environ.get("PALACE_DIR"):                     # after publication = after the listener's veto window
            for slug in new:
                try:
                    palace_ingest_episode(os.path.join(EPISODES, slug), log)
                except Exception as e:
                    print(f"WARNING: optional palace ingest failed for {slug} ({e}) — "
                          f"rerun: podcast.py palace episodes/{slug}")
        print(f"=== done ({len(new)} new episode(s){', FAILED: ' + ', '.join(failed) if failed else ''}) ===")
        sys.exit(1 if failed else 0)
