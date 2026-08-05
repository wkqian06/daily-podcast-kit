#!/usr/bin/env python3
"""Synthesize the spoken intro for an issue with Kokoro (fully local, GPU if present).

Usage: make_audio.py <narration.json> <out_dir>
narration.json: {"en": "...", "zh": "..."}
Writes <out_dir>/audio/intro-en.mp3 and intro-zh.mp3 and prints their durations.

Notes
- The Chinese pipeline drops English tokens unless an en_callable is supplied; ours routes
  them through the English model so terms like LLM / SAR / GRL stay audible.
- The zh model lives in a separate repo with its own weights filename, and KModel wants
  LOCAL paths, so the files are fetched via hf_hub_download first.
"""
import json
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")

import numpy as np
import soundfile as sf
from huggingface_hub import hf_hub_download
from kokoro import KModel, KPipeline

def pick_device():
    """CPU unless a GPU is both present and has room. Someone else's machine may have no
    GPU at all, or one that another process has filled — neither should stop an episode."""
    want = os.environ.get("KOKORO_DEVICE", "").strip()
    if want:
        return want
    try:
        import torch
        if not torch.cuda.is_available():
            return "cpu"
        free, _ = torch.cuda.mem_get_info()
        return "cuda" if free > 1_500_000_000 else "cpu"      # need ~1.5 GB headroom
    except Exception:
        return "cpu"


DEVICE = pick_device()

EN_REPO = "hexgrad/Kokoro-82M"
ZH_REPO = "hexgrad/Kokoro-82M-v1.1-zh"
EN_VOICE = os.environ.get("KOKORO_EN_VOICE", "af_heart")
ZH_VOICE = os.environ.get("KOKORO_ZH_VOICE", "zf_001")
SR = 24000


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def encode(wav, stem):
    """Two speech-optimised mono files from the same source.

    AAC/m4a first (iOS streams it best and it is smaller at equal quality), MP3 as a
    universal fallback. Both at 32 kbps mono, 24 kHz — plenty for narration and about
    a third the size of the old 64 kbps mp3, which mattered because the long podcast
    was stalling on mobile connections.
    """
    out = []
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", wav,
                    "-c:a", "aac", "-b:a", "32k", "-ac", "1", "-ar", "24000",
                    "-movflags", "+faststart", stem + ".m4a"], check=True)
    out.append(stem + ".m4a")
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", wav,
                    "-c:a", "libmp3lame", "-b:a", "32k", "-ac", "1", "-ar", "24000",
                    stem + ".mp3"], check=True)
    out.append(stem + ".mp3")
    os.remove(wav)
    return out


def split_sentences(text, max_chars):
    """Kokoro silently truncates past ~510 phoneme tokens — a 431-character Chinese
    paragraph came out as 28s instead of ~95s. Synthesize sentence by sentence."""
    import re
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


def synth(pipeline, text, voice, out_wav, max_chars):
    """Returns (duration, segments). Because we synthesize sentence by sentence, the
    per-sentence timings are exact rather than estimated — that is what lets the page
    highlight the transcript in step with the audio and seek by clicking a sentence."""
    pieces = []
    segments = []
    gap = np.zeros(int(SR * 0.28), dtype="float32")     # a breath between sentences
    cursor = 0.0
    for sentence in split_sentences(text, max_chars):
        chunks = [np.asarray(r.audio, dtype="float32") for r in pipeline(sentence, voice=voice)]
        if not chunks:
            continue
        seg = np.concatenate(chunks)
        dur = len(seg) / SR
        segments.append({"start": round(cursor, 2),
                         "end": round(cursor + dur, 2),
                         "text": " ".join(sentence.split())})
        pieces.append(seg)
        pieces.append(gap)
        cursor += dur + len(gap) / SR
    if not pieces:
        raise RuntimeError("synthesis produced no audio")
    audio = np.concatenate(pieces[:-1])                  # drop the trailing gap
    sf.write(out_wav, audio, SR)
    return len(audio) / SR, segments


def main():
    narr_path, out_dir = sys.argv[1], sys.argv[2]
    narr = json.load(open(narr_path, encoding="utf-8"))
    audio_dir = os.path.join(out_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    durations = {}

    print(f"  device: {DEVICE}", file=sys.stderr)
    en_pipe = KPipeline(lang_code="a", repo_id=EN_REPO, device=DEVICE)
    if narr.get("en", "").strip():
        wav = os.path.join(audio_dir, "intro-en.wav")
        durations["en"], _ = synth(en_pipe, narr["en"], EN_VOICE, wav, 260)
        encode(wav, os.path.join(audio_dir, "intro-en"))

    # Long-form walkthrough (~10 min). Same voice, same sentence-splitting.
    if narr.get("podcast", "").strip():
        wav = os.path.join(audio_dir, "podcast-en.wav")
        durations["podcast"], segs = synth(en_pipe, narr["podcast"], EN_VOICE, wav, 140)
        json.dump(segs, open(os.path.join(audio_dir, "segments.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=1)
        encode(wav, os.path.join(audio_dir, "podcast-en"))

    if narr.get("zh", "").strip():
        cfg = hf_hub_download(ZH_REPO, "config.json")
        wts = hf_hub_download(ZH_REPO, "kokoro-v1_1-zh.pth")
        zh_model = KModel(repo_id=ZH_REPO, config=cfg, model=wts).to(DEVICE).eval()
        # keep English technical terms audible inside the Chinese narration
        en_phon = KPipeline(lang_code="a", repo_id=EN_REPO, model=False)

        def en_callable(t):
            return next(en_phon(t)).phonemes

        zh_pipe = KPipeline(lang_code="z", repo_id=ZH_REPO, model=zh_model,
                            en_callable=en_callable, device=DEVICE)
        wav = os.path.join(audio_dir, "intro-zh.wav")
        durations["zh"], _ = synth(zh_pipe, narr["zh"], ZH_VOICE, wav, 60)
        encode(wav, os.path.join(audio_dir, "intro-zh"))

    json.dump({k: round(v, 1) for k, v in durations.items()},
              open(os.path.join(audio_dir, "durations.json"), "w"))
    stems = {"en": "intro-en", "zh": "intro-zh", "podcast": "podcast-en"}
    for key, secs in durations.items():
        sizes = " / ".join(
            f"{ext}:{os.path.getsize(os.path.join(audio_dir, stems[key] + ext))/1024:.0f}KB"
            for ext in (".m4a", ".mp3")
            if os.path.exists(os.path.join(audio_dir, stems[key] + ext)))
        print(f"  {stems[key]}  {secs:.1f}s ({secs/60:.1f} min)  {sizes}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if DEVICE == "cuda" and "out of memory" in str(e).lower():
            print("  CUDA out of memory — retrying on CPU", file=sys.stderr)
            os.environ["KOKORO_DEVICE"] = "cpu"
            DEVICE = "cpu"
            main()
        else:
            raise
