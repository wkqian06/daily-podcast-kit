# Web page — HuggingFace static Space

The public-facing target: every episode accumulates on one page you can page through like
slides, with a synced transcript, an optional second language, comprehension questions and
citations. Static Spaces are free and need no server.

The same Space also serves the podcast-owned literature report at `weekly/index.html`. Prepare
it with `python scripts/podcast.py weekly`; the report has its own archive, bilingual issue data,
paper findings, open questions and optional weekly audio. KnowledgePalace is only an optional
retrieval and ingestion tool for that workflow.

Optional and independent of the private RSS feed. Run either, or both.

---

## What the page does

* **One episode at a time**, with prev/next and a drawer listing everything. Opens on the
  newest; `#004` in the URL deep-links an episode.
* **The transcript follows the audio** and auto-scrolls, using per-sentence timings measured
  during synthesis rather than estimated. Clicking any sentence seeks to it.
* **A second-language transcript**, aligned sentence for sentence, behind a toggle that
  remembers your choice.
* **Comprehension questions** with hidden answers.
* **Further reading**, every link verified to exist before publication.

---

## Setup

### 1. Get a token

Create a **write** token at <https://huggingface.co/settings/tokens>. In `config.env`:

```bash
HF_TOKEN="hf_..."
PODCAST_SPACE="your-username/daily-podcast"     # created on first publish
PODCAST_TITLE="Your Show"
PODCAST_BLURB="One line about what it is."
```

### 2. Publish

```bash
python scripts/build_site.py site
python scripts/podcast.py align site/index.html
python scripts/podcast.py hf site
```

Or simply `python scripts/podcast.py publish`, which runs these three and the RSS step.

The Space is created automatically. A new one takes a moment to build the first time.

### 3. Check it on a phone

Not optional. Two of the worst bugs in `LESSONS.md` were invisible on desktop.

---

## Three things that will bite you

### The Space must be `static`

Gradio and Docker Spaces need a PRO account and fail with `402 Payment Required`. The page
is pure HTML and needs no server, so keep `sdk: static` in the Space README frontmatter —
`podcast.py hf` writes this for you.

### Audio can never be a plain file `src`

HuggingFace signs each CDN URL for one byte range, which stalls audio forever on iOS Safari
while working fine on desktop. `build_site.py` inlines small files as `data:` URIs and
fetches larger ones whole into a blob. Full explanation in `LESSONS.md` §1.

If you rewrite the player, keep this property. `LESSONS.md` §11 shows how to verify it.

### `podcast.py align` must run last

HuggingFace processes served HTML in 8192-byte chunks and mangles any multi-byte character
straddling a boundary — one character somewhere in the page becomes `�`, only on the live
site, and it moves as you edit content. `podcast.py align` nudges the byte layout so no
character sits on a boundary. Anything that runs after it undoes the fix. `LESSONS.md` §2.

---

## Links inside the page

HuggingFace renders static Spaces inside a sandboxed iframe. A link without a target
navigates the frame to `huggingface.co`, which refuses to be framed, and the reader gets
"refused to connect" while the address bar never changes.

`target="_top"` does not help — the sandbox grants `allow-popups` but not
`allow-top-navigation`. Use `target="_blank" rel="noopener"`, or a page-wide
`<base target="_blank">`. `LESSONS.md` §8.

---

## Feedback

Each Space has a Community tab. The page links to it once, quietly, in the appendix. It is
worth wiring up: reader requests there are the highest-signal input to `prompts/queue.md`,
which is where topics come from before anything else.

To collect them programmatically, `huggingface_hub`'s `get_repo_discussions` reads the tab
and you can fold the results into the nightly prompt.
