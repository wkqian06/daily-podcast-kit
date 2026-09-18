# Lessons

Every item here is a bug that shipped, or nearly shipped, and cost real debugging. They are
not obvious from reading the code, which is why they are written down. If you change the
audio delivery, the transcript sync or the publishing step, read the relevant section first.

---

## 1. HuggingFace signs each CDN URL for ONE byte range — this breaks audio on iOS

**Symptom.** Audio plays on desktop. On an iPhone the player spins on "loading" forever, with
no error in the console.

**Cause.** HuggingFace serves every Space file via a 302 redirect to a signed CDN URL, and the
signature is bound to the exact byte range that produced it. Its policy literally contains
`"ByteRange":{"ExpectedHeader":"bytes=0-1"}`. Verified with curl: one signed URL answers `206`
for `bytes=0-1` and **`403`** for `bytes=2-100000`.

Desktop Chrome re-requests the original URL for each range and gets a fresh signature, so it
works. iOS Safari reuses the redirect target for the media element, so its second range request
is rejected and the element stalls forever.

There is **no non-redirecting path** on HF static Spaces. Even `index.html` 302s.

**Fix, implemented in `build_site.py`.** Never let the media element issue range requests:

* files under `INLINE_LIMIT` (700 KB) are embedded as `data:` URIs — zero network requests;
* anything larger gets a "Load audio" button that `fetch()`es the whole file in ONE plain GET
  (no `Range` header) and plays it from `URL.createObjectURL(blob)`.

**Never** write `<audio src="audio/episode.m4a">`. It looks fine and fails on half your audience.

**Things that are NOT the cause**, all checked and ruled out: file size, missing `faststart`
(the `moov` atom was verified to be at the front), broken Range support in general, bad MIME type.

---

## 2. HuggingFace mangles UTF-8 on 8 KB boundaries

**Symptom.** A single character in the middle of the page renders as `�` on the live site,
while the local file is perfectly fine. Moves or disappears when the page length changes.

**Cause.** HF injects a small `<script>` into `<head>` when serving, and its HTML processing
walks the file in 8192-byte chunks. Any multi-byte UTF-8 character straddling a boundary comes
back mangled. Measured: a Chinese character occupying local bytes 8190–8192 was destroyed.
The boundaries are multiples of 8192 **in the stored file**, not in the served stream.

Layout-dependent, so it appears and disappears as you edit content — which makes it look random.

**Fix.** `podcast.py align` inserts single spaces at `><` tag boundaries until no character
sits on a multiple of 8192. Whitespace between tags is inert, so rendering is unchanged.
**Run it last** in the pipeline: it shifts byte offsets, so anything that runs after it undoes it.

---

## 3. Kokoro silently truncates long text

**Symptom.** A 431-character paragraph produced 28 seconds of audio instead of the expected 95.
No error, no warning. The rest is simply missing.

**Cause.** The model has a context limit of roughly 510 phoneme tokens and drops the overflow.

**Fix.** `podcast.py audio` splits on sentence boundaries and synthesizes piece by piece, joining
with 0.28 s gaps. Keep chunks well under the limit — 140 characters is the setting used here,
which also gives finer transcript-highlight granularity.

**Always check** that output duration is roughly `words / 150` minutes. If it is far short, this
is why.

---

## 4. Get the transcript timings from the synthesizer, not from an estimate

Because the audio is synthesized sentence by sentence anyway, the exact start and end of each
sentence is known for free. `podcast.py audio` writes `audio/segments.json` with measured timings.

Do not estimate timings from word counts. Measured timings make the highlight track perfectly
and never drift, and clicking a sentence seeks to precisely the right place.

Related bug that this exposed: the sentence splitter was re-joining pieces with no space,
producing `dead.And` in the transcript. The regex consumed the separating whitespace.

---

## 5. Translate per segment, never the whole script

If you translate the transcript as one block and re-split it, every timestamp is wrong and both
the highlight and click-to-seek break.

`podcast.py translate` translates segment by segment and **refuses to write output unless the
count matches exactly**. `build_site.py` re-checks the length and drops the translation if it
disagrees, degrading to single-language with no toggle shown. A misaligned translation is worse
than no translation.

It also batches (30 segments), caches each batch so a failed run resumes cheaply, and retries
once. Long runs matter: a full episode takes several minutes.

---

## 6. CSS specificity will fight your language toggle

The page's own language switch is typically `.lang-zh{display:none}`. If you then add
`.audio-intro{display:flex}` **later in the stylesheet**, it wins — equal specificity, later rule
— and hidden elements become visible. This shipped: both language versions of the player were
displayed at once.

**Fix.** Never put a `display` rule on a container that also carries a language class. Put the
language classes on the inner labels instead, or scope the rule to an ancestor
(`body.zh .seg .t-en{display:none}`) so it out-specifies.

---

## 7. Two copies of a script cancel each other out

**Symptom.** A button does nothing. No console error. The handler is definitely attached.

**Cause.** The injector added a marked `<script>` but did not remove an earlier **unmarked**
copy. Both bound a click handler to the same button: the first called `play()`, the second saw
`paused === false` and called `pause()`. Net effect: nothing, silently.

**Fix.** Any code that injects a script must strip previous injections, marked *and* unmarked,
before adding its own. Test idempotency by running the injector twice and counting.

---

## 8. Links inside a HuggingFace Space need an explicit target

Static Spaces render inside a sandboxed iframe. A plain `<a href="https://...">` navigates the
**frame**, and `huggingface.co` refuses to be framed, so the reader gets "refused to connect"
and the address bar never changes.

`target="_top"` does **not** help: the sandbox grants `allow-popups` and
`allow-popups-to-escape-sandbox` but **not** `allow-top-navigation`.

**Use `target="_blank" rel="noopener"`**, or a `<base target="_blank">` for the whole page.

---

## 9. An auto-writing agent will invent plausible URLs

The very first self-selected episode produced six further-reading links, one of which was a
Wikipedia URL for a real book at a page that does not exist. The citation looked completely
normal.

`podcast.py links` probes every citation before anything is synthesized and drops the dead ones.
Critically, it distinguishes **dead** from **blocked**: publishers answer bots with 400/401/402/
403/429 all the time (Nature, phys.org, Science), and treating those as dead would strip your
best sources. Only a real 404/410 or a connection failure counts.

---

## 10. Publish what is ready; never generate filler at publish time

The publish step and the authoring step are separate jobs for a reason:

* **Nightly**, decide and produce tomorrow's episode. This is the expensive, failure-prone part,
  and doing it the night before leaves a window to read, veto or edit.
* **In the morning**, build and publish whatever is ready. If nothing is, say so and stop.

Do not make the morning job generate content — you will ship something nobody reviewed. And do
not let a failure at any stage publish a partial episode: every failure path here exits rather
than degrading.

---

## 11. Verify in a browser, not by reading the HTML

Two separate bugs above (numbers 1 and 7) were invisible in the markup and produced no console
error. Both were found by driving a real browser with Playwright: clicking the button and
asserting `currentTime` advances.

Also emulate a phone. A desktop-headless check passed while the real iPhone failed, because the
failure was iOS-specific. `p.chromium.launch()` with `p.devices["iPhone 13"]` catches layout and
lazy-loading problems; it will not catch true WebKit-only issues, so treat a pass as necessary
rather than sufficient.

---

## 12. Cloudflare's edge blocks Python before your Worker sees it

**Symptom.** `curl` uploads fine. The identical request from a Python script gets `403`.

**Cause.** Cloudflare's bot protection rejects the default `Python-urllib/3.x` User-Agent at
the edge. The request never reaches the Worker, so there is nothing in your Worker logs and
the status code does not match anything your code returns.

**Fix.** Send a browser User-Agent from any client you write. `podcast.py rss` does.

**Diagnostic worth remembering:** when a status code appears that your own code cannot
produce, suspect the layer in front of it. Our Worker returns 404 for unauthorized, never
403 — so a 403 immediately located the problem outside our code.

---

## 13. A new workers.dev subdomain has no TLS certificate for about a minute

**Symptom.** DNS resolves to Cloudflare, but every request dies with
`SSL alert 40 / handshake failure`. Looks exactly like a broken configuration.

**Cause.** The certificate for a freshly registered `*.workers.dev` subdomain takes a short
while to provision.

**Fix.** Wait and poll. Do not start changing config.

```bash
until curl -sf https://<worker>.<sub>.workers.dev/health; do sleep 30; done
```

Related first-run friction, neither of which wrangler can do non-interactively: R2 must be
enabled in the dashboard (`code: 10042` otherwise), and a workers.dev subdomain must be
registered — that one *can* be done through the API, see `docs/PRIVATE_RSS.md`.

---

## 14. Do not percent-encode slashes inside object keys

`encodeURIComponent("audio/ep1.m4a")` yields `audio%2Fep1.m4a`. Our own Worker happened to
decode it, but stricter HTTP clients reject `%2F` in a path, and podcast apps are a
long tail of stricter clients.

Encode each path segment separately and keep the slashes.

---

## 15. The transcript tag is advisory; apps mostly ignore it

The feed advertises captions with `<podcast:transcript>`, built from measured synthesis
timings, so they are exact. Whether anyone shows them is another matter:

* **Snipd** ignores the tag and runs its own AI transcription, rate-limited on the free plan.
  So transcripts frequently do not appear — for any show, not just yours.
* **Podverse** and other Podcasting 2.0 apps read the tag.
* **Apple Podcasts** generates its own and ignores the tag.

And **no third-party app can display a transcript on CarPlay at all** — Apple's templates do
not expose synced text to third-party audio apps.

The lesson generalises: when a spec says a field exists, that is not evidence any client
uses it. Before promising a feature that depends on a client honouring metadata, check what
the clients actually do.

---

## 16. A growing prompt kills the nightly job on Windows, months later

`prepare` passed its prompt to the `claude` CLI as an argument. It worked for three episodes,
then one night:

```
FileNotFoundError: [WinError 206] The filename or extension is too long
```

Nothing in the repository had changed. What changed was the KnowledgePalace library: with an
empty queue the topic comes from the library's open questions, so `palace_header(with_gaps=True)`
appends `gaps/INDEX.md` to the prompt. That file grows every time a gap is recorded. It crossed
25 KB, the whole prompt reached 35 KB, and Windows caps an *entire command line* at 32767
characters.

**The failure is delayed and looks unrelated.** The job runs unattended, the traceback names
`CreateProcess` rather than anything about prompts, and the only thing that "broke" was a file
in a different repository getting longer. A queued topic still worked, because without gaps the
prompt is 9 KB — so it failed on exactly the nights nobody had queued anything.

**Fix.** Send the prompt on stdin; `claude -p` reads it there and no limit applies:

```python
cmd = [exe, "-p", "--allowedTools", *tools, ...]
subprocess.run(cmd, input=prompt, ...)
```

The general rule: any prompt built by concatenating files you do not control is unbounded.
Never put one on a command line — not on Windows, and not on Linux, where `ARG_MAX` is larger
but equally finite.
