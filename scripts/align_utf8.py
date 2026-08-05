#!/usr/bin/env python3
"""Work around a HuggingFace static-Space serving bug that corrupts Chinese text.

HF injects a small <script> into <head> when serving, and its HTML processing walks
the file in 8192-byte chunks. Any UTF-8 multi-byte character that straddles a chunk
boundary comes back mangled (the leading bytes become U+FFFD). Observed live:
issue #1's 量 occupied local bytes 8190-8192 and came back as U+FFFD + a stray byte;
issue #2 lost one at the 16384 boundary. issue #3 was clean only because no character
happened to sit on a boundary. Boundaries are multiples of 8192 in the stored file.

Fix: nudge the byte layout so no multi-byte character spans a boundary, by inserting
single spaces at tag boundaries (`><`) before each offending offset. Whitespace between
tags is inert in HTML, so rendering is unchanged. HF's injected prefix is accounted for.

Usage: hf_align.py <index.html> [--inject-bytes N]
"""
import sys

CHUNK = 8192
HF_INJECT = 0            # empirically the chunking uses OUR file's offsets, not the
                         # served stream's: issue #1's 量 sat at 8190-8192 locally and
                         # was mangled, so boundaries are plain multiples of 8192 here.
MAX_PASSES = 400


def straddles(data, inject):
    """First chunk boundary that lands inside a multi-byte character, or None."""
    k = 1
    while k * CHUNK - inject < len(data):
        pos = k * CHUNK - inject          # offset in OUR file that HF sees as a boundary
        if 0 < pos < len(data) and 0x80 <= data[pos] <= 0xBF:
            return pos
        k += 1
    return None


def realign(data, inject=HF_INJECT):
    inserted = 0
    for _ in range(MAX_PASSES):
        pos = straddles(data, inject)
        if pos is None:
            return data, inserted
        j = data.rfind(b"><", 0, pos)     # a safe, inert place to add a byte
        if j == -1:
            j = data.rfind(b">", 0, pos)
            if j == -1:
                break
        data = data[:j + 1] + b" " + data[j + 1:]
        inserted += 1
    return data, inserted


def main():
    path = sys.argv[1]
    inject = HF_INJECT
    if "--inject-bytes" in sys.argv:
        inject = int(sys.argv[sys.argv.index("--inject-bytes") + 1])

    data = open(path, "rb").read()
    fixed, n = realign(data, inject)
    if n:
        open(path, "wb").write(fixed)
    left = straddles(fixed, inject)
    status = "clean" if left is None else f"STILL STRADDLING at {left}"
    print(f"hf_align: {n} pad byte(s) inserted, {status} — {path}")
    return 0 if left is None else 1


if __name__ == "__main__":
    sys.exit(main())
