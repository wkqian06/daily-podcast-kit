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
| `script.txt` | you | the narration, in paragraphs. Also rendered as the on-page transcript. |
| `episode.json` | you | metadata, further reading, quiz. Schema below. |
| `materials/` | the listener | optional source files (PDFs etc.) they want covered |
| `narration.json` | pipeline | the script collapsed for the synthesizer |
| `audio/` | pipeline | `podcast-en.m4a`, `.mp3`, `durations.json`, `segments.json` |

`episode.json`:

```json
{
  "number": 4,
  "slug": "short-kebab-case",
  "title": "a real title, not a topic label",
  "subtitle": "one line saying what the argument is",
  "date": "YYYY-MM-DD",
  "summary": "3-5 sentences: what it covers and why it is worth ten minutes",
  "further_reading": [{"title": "...", "url": "...", "note": "what it is, and whether it is free"}],
  "quiz": [{"q": "...", "a": "..."}]
}
```

---

## The two jobs

```
nightly   scripts/prepare_episode.sh   pick a topic if none is queued, write it, check the
                                       citations, synthesize, translate. Publishes nothing.
morning   scripts/daily_publish.sh     build the site, publish, verify it serves.
```

Nightly runs the day **before** publication on purpose: it leaves a window for the listener to
read, veto or edit. Do not merge these two jobs.

---

## Invariants — do not break these

1. **Audio is never a plain file `src`.** Inline it as a `data:` URI, or fetch it whole into a
   blob. See LESSONS §1. Breaking this makes audio fail on every iPhone, silently.
2. **`align_utf8.py` runs last.** It shifts byte offsets; anything after it undoes it. LESSONS §2.
3. **Translations are per segment and count-checked.** A misaligned translation destroys the
   transcript sync. LESSONS §5.
4. **Every citation is probed before synthesis.** Auto-written episodes invent URLs. LESSONS §9.
5. **Any failure exits.** Never publish a partial or unreviewed episode. LESSONS §10.
6. **Verify in a real browser, emulating a phone.** Reading the HTML is not verification.
   LESSONS §11.

---

## Adding an episode by hand

```bash
mkdir -p episodes/009
# write episodes/009/script.txt and episodes/009/episode.json
python3 scripts/check_links.py episodes/009      # drops dead citations
python3 -c "import json;s=open('episodes/009/script.txt').read();\
json.dump({'podcast':' '.join(s.split())},open('episodes/009/narration.json','w'))"
python3 scripts/make_audio.py episodes/009/narration.json episodes/009
python3 scripts/translate_segments.py episodes/009        # optional
python3 scripts/build_site.py site && python3 scripts/align_utf8.py site/index.html
python3 scripts/publish_hf.py site
```

Or just drop `script.txt` + `episode.json` in place and let the nightly job finish it.

---

## Writing

`prompts/pick_topic.md` holds the selection rules; `prompts/taste.md` holds what this particular
listener responds to. **taste.md is the authority on style and is meant to be edited constantly** —
every time the listener reacts to an episode, write down what you learned, including when your
guess was wrong. It is what lets topic selection get better instead of drifting.

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
| one character shows as `�` on the live site only | LESSONS §2 — did `align_utf8.py` run last? |
| audio much shorter than `words / 150` minutes | LESSONS §3 — synthesizer truncation |
| highlight drifts or click-to-seek is wrong | LESSONS §4, §5 — timings or translation alignment |
| both languages visible at once | LESSONS §6 — CSS specificity |
| a button does nothing, no console error | LESSONS §7 — duplicate script |
| link opens "refused to connect" inside the Space | LESSONS §8 — needs `target="_blank"` |
| a citation 404s | LESSONS §9 — `check_links.py` should have caught it |
