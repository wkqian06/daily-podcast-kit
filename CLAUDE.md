# Operating this repo

You are running a daily ten-minute podcast. Each episode is written, narrated by a local
text-to-speech model, and published as a single static page that accumulates every episode.

Read `LESSONS.md` before changing anything in `scripts/`. It documents failures that are not
visible in the code and that have already shipped once.

---

## What an episode is

A directory `episodes/NNN/` containing:

| file | written by | what it is |
|---|---|---|
| `topic.md` | you | the proposal: two or three candidates, and the listener's `CHOICE:` line |
| `script.txt` | you | the narration, in paragraphs. Also rendered as the on-page transcript. |
| `episode.json` | you | metadata, further reading, quiz. Schema below. |
| `audio/` | pipeline | `podcast-en.m4a`, `.mp3`, `durations.json`, `segments.json` |

Papers the listener obtained for you live outside the episode, in `materials/NNN/`. They are
reading input, not episode content, and nothing publishes from them.

`episodes/` and `materials/` are gitignored: what the kit produces belongs to the listener,
not to the repository, so a clone starts with neither and every job handles that. The one
exception is `episodes/001-example/`, a real episode tracked as the format reference.

**An episode directory is `NNN`.** A name that is not a number is documentation, and
`episode_dirs()` in `podcast.py` plus the same test in `build_site.py` are what keep the
example from being numbered over, narrated, rendered onto the page or published.

`episode.json`:

```json
{
  "number": 4,
  "slug": "short-kebab-case",
  "title": "a real title, not a topic label",
  "subtitle": "one line saying what the argument is",
  "date": "YYYY-MM-DD",
  "summary": "3-5 sentences: what it covers and why it is worth ten minutes",
  "further_reading": [{"title": "...", "url": "...", "note": "what it is, whether it is free, and ending with one of 'Read: full text.' / 'Read: abstract only.' / 'Read: not obtained.'"}],
  "quiz": [{"q": "...", "a": "..."}]
}
```

Three more keys exist only when the run puts them there: the writer adds `palace` (coverage,
queries, analysis, references, ingest) when `PALACE_DIR` is set, `prepare --write` stamps `topic_source`
(`listener` or `library`), and a completed ingest leaves a `knowledge_palace_ingest`
receipt. `prompts/write_episode.md` has the exact shape; `docs/PALACE.md` says what they are for.

---

## Two delivery targets, both optional

| target | what it is | enable with | docs |
|---|---|---|---|
| web page | one public page, all episodes, synced transcript | `PODCAST_SPACE` | `docs/WEB_PAGE.md` |
| private feed | unlisted RSS for podcast apps and the car | `RSS_BASE` + `RSS_UPLOAD_TOKEN` | `docs/PRIVATE_RSS.md` |

They are independent: either can fail without stopping the other, and running neither is a
configuration error the publish job refuses. The feed's Worker lives in `worker/`.

## The jobs, and the confirmation between them

```
nightly   python scripts/podcast.py prepare           propose 2-3 candidates for tomorrow into
                                                      episodes/NNN/topic.md, then stop.
you       fill in the CHOICE: line                    and drop any paper you could not reach
                                                      into materials/NNN/
on demand python scripts/podcast.py prepare --write   write that candidate, check the citations,
                                                      synthesize, translate. Publishes nothing.
morning   python scripts/podcast.py publish           build the site, publish, verify it serves.
```

The topic comes from `prompts/queue.md` first and from the library's open questions second. There
is no third source: with neither, `prepare` ends the night without a proposal rather than inventing
a subject. Nothing is ever narrated before the listener confirms a candidate — the nightly job
cannot write an episode even if it runs unattended for a week.

Everything except the page template lives in `scripts/podcast.py`; the page is `scripts/build_site.py`.
On Windows the two jobs run as Claude routines or Task Scheduler tasks — see `docs/WINDOWS.md`.
With `PALACE_DIR` set, `prepare` compares each episode against the listener's KnowledgePalace
library and `publish` may ingest explicitly selected papers. Episodes and operational records stay
in this repository; KnowledgePalace receives no podcast project or material — `docs/PALACE.md`.

Nightly runs the day **before** publication on purpose: it leaves a window for the listener to
read, veto or edit. Do not merge these steps, and never schedule `prepare --write`. `publish` refuses to run within an hour of
`prepare` finishing — a scheduler catching up after sleep would otherwise ship an unreviewed
episode — and `publish --now` overrides that after a review.

---

## Invariants — do not break these

1. **Audio is never a plain file `src`.** Inline it as a `data:` URI, or fetch it whole into a
   blob. See LESSONS §1. Breaking this makes audio fail on every iPhone, silently.
2. **`podcast.py align` runs last.** It shifts byte offsets; anything after it undoes it. LESSONS §2.
3. **Translations are per segment and count-checked.** A misaligned translation destroys the
   transcript sync. LESSONS §5.
4. **Every citation is probed before synthesis.** Auto-written episodes invent URLs. LESSONS §9.
5. **Any failure exits.** Never publish a partial or unreviewed episode. LESSONS §10.
6. **Nothing is narrated before the listener confirms a topic.** `prepare` proposes and stops;
   only `prepare --write`, run by hand after the `CHOICE:` line is filled in, writes an episode.
7. **Verify in a real browser, emulating a phone.** Reading the HTML is not verification.
   LESSONS §11.
8. **The Worker serves audio; never hand out a storage URL.** Per-range signed URLs stall
   podcast clients that seek. LESSONS §1, `docs/PRIVATE_RSS.md`.
9. **Any HTTP client you write sends a browser User-Agent.** Cloudflare's bot protection
   rejects `Python-urllib` with 403 at the edge, before your Worker sees it.

---

## Adding an episode by hand

```bash
mkdir -p episodes/009
# write episodes/009/script.txt and episodes/009/episode.json — a directory that already has both
# skips the proposal step entirely
python scripts/podcast.py links episodes/009        # drops dead citations
python scripts/podcast.py audio episodes/009        # Kokoro -> audio/, with measured timings
python scripts/podcast.py translate episodes/009    # optional
python scripts/build_site.py site && python scripts/podcast.py align site/index.html
python scripts/podcast.py hf site
```

`python scripts/podcast.py publish` does the last three lines for every episode, plus the RSS feed.

Or just drop `script.txt` + `episode.json` in place and let the nightly job finish it.

---

## Writing

`prompts/queue.md` holds topics the listener asked for, taken top-down before any other source.
`prompts/propose_topic.md` holds the selection rules and the shape of a proposal;
`prompts/write_episode.md` holds the writing and `episode.json` rules.

Craft rules that matter, learned the hard way:

* Write for the **ear**. Short sentences, one idea each. No markdown, URLs, parentheses,
  bullet symbols or em-dashes — the synthesizer reads them or stumbles.
* Spell out anything that reads oddly aloud: "about twenty percent better", not "+20%".
* Have an **argument**, not a summary. If you cannot state it in one sentence, pick another topic.
* Say plainly where evidence is thin, and where the popular framing is wrong.
* Never oversell. If a result is promising but narrow, say so.
* Quiz questions test the reasoning the episode turns on, never recall. Each answer should
  teach something rather than confirm a fact.

---

## Debugging checklist

| symptom | look at |
|---|---|
| audio stalls on phone, fine on desktop | LESSONS §1 — is it a plain file `src`? |
| one character shows as `�` on the live site only | LESSONS §2 — did `podcast.py align` run last? |
| audio much shorter than `words / 150` minutes | LESSONS §3 — synthesizer truncation |
| highlight drifts or click-to-seek is wrong | LESSONS §4, §5 — timings or translation alignment |
| both languages visible at once | LESSONS §6 — CSS specificity |
| a button does nothing, no console error | LESSONS §7 — duplicate script |
| link opens "refused to connect" inside the Space | LESSONS §8 — needs `target="_blank"` |
| a citation 404s | LESSONS §9 — `podcast.py links` should have caught it |
| podcast app stalls or will not seek | `docs/PRIVATE_RSS.md` — is something handing out a storage URL? |
| publish script gets 403 from Cloudflare | send a browser User-Agent; the edge blocks Python's default |
| `SSL alert 40` on a new Worker | the workers.dev TLS cert takes ~1 min; poll `/health` |
| `code: 10042` creating a bucket | R2 is not enabled yet; enable it in the dashboard |
| transcripts do not show in a podcast app | usually the app, not the feed — `docs/PRIVATE_RSS.md` |
| `WinError 206` / `filename or extension is too long` | LESSONS §16 — the prompt must go on stdin, not argv |

## Literature weekly

The podcast project owns episodes and weekly report selection, editing, rendering, audio and operational records. Read `docs/WEEKLY.md` and `prompts/weekly.md` for issue preparation. Run `python scripts/podcast.py weekly --topic "..."` to install a new issue; `--draft FILE` is the deterministic handoff after review and `--audio` produces a weekly recording from the draft script. KnowledgePalace is an optional callable tool for retrieval, evidence and paper ingestion; never create podcast projects, materials, episodes or reports there. `build_site.py` includes `weekly/` in its output; building does not publish or schedule a weekly run.
