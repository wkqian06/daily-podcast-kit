# daily-podcast-kit

A daily ten-minute podcast that writes itself, narrates itself and publishes itself — and gets
better at choosing topics as you react to it.

Every episode is one page section with:

* **audio** narrated by a local text-to-speech model, so nothing leaves your machine to make it;
* a **transcript that highlights in step with the audio**, using timings measured during
  synthesis rather than estimated, and where clicking any sentence seeks to it;
* an optional **second-language transcript**, aligned sentence for sentence, toggled by a switch;
* **comprehension questions** with hidden answers, written to test the reasoning rather than recall;
* **further reading**, with every link verified to exist before publication.

## Two ways to receive it, both optional

| | what you get | cost | docs |
|---|---|---|---|
| **Web page** | one page, all episodes, synced transcript, quiz, sources | free | [docs/WEB_PAGE.md](docs/WEB_PAGE.md) |
| **Private RSS** | an unlisted feed for any podcast app, and the car | free tier | [docs/PRIVATE_RSS.md](docs/PRIVATE_RSS.md) |

Run either, or both. They are independent — one failing never stops the other. The web page is a
static HuggingFace Space; the feed is a Cloudflare Worker in front of R2, in `worker/`.

---

## How it runs

```
nightly    scripts/prepare_episode.sh    pick tomorrow's topic if none is queued, research it,
                                         write it, verify the citations, synthesize, translate
morning    scripts/daily_publish.sh      build, publish, confirm the site actually serves
```

Nightly runs the day before publication on purpose: it gives you a window to read the episode,
change it, or throw it away before anyone sees it.

If you want to choose the topic, drop `script.txt` and `episode.json` into `episodes/NNN/` and
the nightly job will finish the production for you. If you want an episode about specific
material, put the PDFs in `episodes/NNN/materials/` and ask your agent to write it. If you do
neither, the agent picks something itself.

**It never invents filler.** If nothing is ready, the morning job rebuilds the same site, says
so in the log, and exits.

---

## Requirements

* Python 3.10+
* An `anthropic`-authenticated `claude` CLI on `PATH` (topic selection, writing, translation)
* For the web page: a HuggingFace account and a write token (free)
* For the private feed: a Cloudflare account with R2 enabled (free tier; a card is required
  to enable it even though a personal podcast stays well inside the free allowance)
* Node, for the Worker and for the browser verification in `LESSONS.md`
* A GPU helps: ten minutes of audio synthesizes in about thirty seconds on one, but CPU works

```bash
pip install -r requirements.txt
cp config.env.example config.env    # then fill it in
```

See `SETUP.md` for the first run.

---

## Repository layout

```
CLAUDE.md            how an agent should operate and extend this — read this first
LESSONS.md           bugs that shipped, and why the code is shaped the way it is
SETUP.md             first-run walkthrough
prompts/
  pick_topic.md      the selection rules the agent applies when choosing for itself
  taste.example.md   a template for recording what your listener actually responds to
docs/
  WEB_PAGE.md        the public page target, and its three gotchas
  PRIVATE_RSS.md     the private feed target: Cloudflare setup, start to finish
worker/
  src/index.js       the Worker: RSS, token auth, byte-range media streaming
  wrangler.toml      deploy config
scripts/
  prepare_episode.sh nightly: choose, write, verify, synthesize
  daily_publish.sh   morning: build, publish to whichever targets are configured
  publish_rss.py     captions from measured timings, upload, refresh the feed
  build_site.py      renders every episode into one paged site
  make_audio.py      Kokoro synthesis; also emits measured per-sentence timings
  translate_segments.py  segment-aligned translation, count-checked
  check_links.py     probes citations, drops dead ones, keeps bot-blocked ones
  publish_hf.py      uploads to a single HuggingFace Space
  align_utf8.py      works around a HuggingFace serving bug; must run last
episodes/
  001-example/       the format, with a real episode's text
```

---

## The part that matters most

`prompts/taste.md` is a living record of what your listener responds to. It starts nearly empty
and you update it every time they react — including, importantly, when your guess was wrong.

In the run this kit came from, the agent inferred from a listener's detailed technical questions
that they wanted deeply technical topics. It proposed four. The listener rejected all four and
asked for a profile of a person instead. That correction went into taste.md, and the selection
rules gained a filter that now runs before every other one: *would this listener want to hear
about this at all?*

Without that file, topic selection does not improve. It just drifts.

---

## Honest limitations

* The narration is synthesized. It is good, not human. Say so on the page.
* An agent choosing its own topics will occasionally choose badly. The nightly/morning split
  exists so you can catch that.
* Everything the agent writes should be treated as needing verification. `check_links.py` catches
  fabricated URLs; it cannot catch a confidently wrong sentence. Read the episodes.
* This publishes to HuggingFace because static Spaces are free and need no server. Any static
  host works; `publish_hf.py` is the only file that knows about HuggingFace, except for the
  workaround in `align_utf8.py`.

---

## Licence

MIT. The prompts and lessons are the valuable part — take them.
