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

## Literature weekly

A bilingual reading-report page lives at `site/weekly/index.html`, with paper findings, limitations, research connections, topic filters, search, an issue archive and optional audio. The podcast project owns its editing and presentation; KnowledgePalace is an optional evidence and ingestion tool. See [docs/WEEKLY.md](docs/WEEKLY.md).

Prepare an issue with `python scripts/podcast.py weekly --topic "your topic"`; use `--audio` when the draft also contains `script.txt`. The command installs a new issue, preserves the archive, rebuilds the site and leaves external publishing to `publish`.

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
                  +------------------------- what feeds it -------------------------+
                  |  prompts/queue.md            a topic you asked for              |
                  |  KnowledgePalace gaps        the library's open questions       |
                  |  neither of the first two    no proposal that night, by design  |
                  +--------------------------------+--------------------------------+
                                                   v
  22:00  podcast.py prepare
         propose     two or three candidates -> episodes/NNN/topic.md, then stop
           +-> each one carries its argument, its sources, and what it could NOT reach
  -- you confirm one ------------------------------+   write your pick after CHOICE:, and put
                                                   |   any paper I could not reach into materials/NNN/
                                                   v
         podcast.py prepare --write
           +-> write          script.txt + episode.json         prompts/write_episode.md
                +-> links     probe every citation, drop the dead      too few left => stop
                     +-> audio       Kokoro, per-sentence timings measured     fails => stop
                          +-> translate    per segment, count-checked              optional
  -- your review window ---------------------------+   read it, edit it, or delete the directory
                                                   v
  09:00  podcast.py publish
         refuse if prepare finished under an hour ago        --now overrides, after a review
           +-> build_site.py   every episode, plus weekly/, into one static site
                +-> align      pad the HTML so no UTF-8 char straddles 8 KB    ALWAYS LAST
                     +-> hf    upload the Space, poll until it serves 200      -> web page
                     +-> rss   audio and captions to the Worker                -> podcast app
                          +-> record in .published, then optional paper ingest into the library

  on demand  podcast.py weekly            docs/WEEKLY.md
         prompts/weekly.md -> weekly/drafts/DATE/issue.json -> mechanical checks
           -> weekly/issues.json, archive kept -> site/weekly/, which the next publish ships
```

Two gates are human: nothing is narrated until you confirm a candidate, and nothing is published
until you have had the night to read it. Every other stage stops the run rather than shipping
something unverified, and the two delivery targets fail independently.

Nightly runs the day before publication on purpose: it gives you a window to read the episode,
change it, or throw it away before anyone sees it.

Put the topic you want on a line of `prompts/queue.md` and the nightly job proposes two or three
angles on it. With the queue empty the candidates come from your KnowledgePalace library's open
questions; with neither, the night ends without a proposal rather than inventing a subject.

Nothing is written until you say so. Read `episodes/NNN/topic.md`, put your pick after `CHOICE:`
and run `prepare --write`. Where a candidate leans on a paper the agent could not open, the
proposal says so by name — drop the PDF into `materials/NNN/` before confirming and the
writing run reads it in full. If you would rather write the episode yourself, drop `script.txt`
and `episode.json` into `episodes/NNN/` and the nightly job finishes the production for you.

**It never invents filler.** If nothing is ready, the morning job rebuilds the same site, says
so in the log, and exits.

---

## Requirements

* Python 3.10+ (Windows works; `docs/WINDOWS.md` covers scheduling it there)
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
test_prepare.py      the one check on the confirmation gate: an empty CHOICE stays unconfirmed
prompts/
  propose_topic.md   the selection rules, and the shape of a proposal
  write_episode.md   how a confirmed candidate becomes a script and an episode.json
  queue.md           one line per topic you want; the nightly job takes the top one
  weekly.md          the editorial rules and JSON contract for a literature issue
docs/
  WEB_PAGE.md        the public page target, and its three gotchas
  PRIVATE_RSS.md     the private feed target: Cloudflare setup, start to finish
  WINDOWS.md         running the two jobs as Claude routines or Task Scheduler tasks on Windows
  WEEKLY.md          the literature weekly: fields, editing flow, audio (in Chinese)
  PALACE.md          optional KnowledgePalace retrieval, analysis and paper-ingest interface
  QUICKSTART.zh-CN.md  中文启动教程：安装、HuggingFace 同步、选题控制、每天的节奏、周报
assets/
  workflow.zh-CN.svg the same flow as a diagram, in Chinese
worker/
  src/index.js       the Worker: RSS, token auth, byte-range media streaming
  wrangler.toml      deploy config
scripts/
  podcast.py         everything but the page. `prepare` (nightly), `publish` (morning) and
                     `weekly`, plus the single steps they are made of: links, audio,
                     translate, align, hf, rss, palace
  build_site.py      renders every episode into one paged site, and copies weekly/ into it
episodes/
  NNN/               your own episodes: topic.md (the proposal), script.txt,
                     episode.json, audio/. Gitignored — the kit is the code, not the output
  001-example/       a real episode, tracked as the format reference. The pipeline skips it:
                     an episode directory is `NNN`, a name that is not a number is docs
materials/           papers you obtained by hand, gitignored for the same reason
  NNN/               the ones episode NNN needed. Reading input; nothing publishes from it
weekly/
  issues.json        every issue, newest first; index.html + weekly.css + weekly.js render them
  drafts/YYYY-MM-DD/ the draft an issue was installed from. Kept as a record, never published
```

---

## The part that matters most

You pick the topic before anything is written. The nightly job researches and proposes; it cannot
narrate a word until you fill in a `CHOICE:` line yourself.

That gate is what makes an agent-run podcast bearable to listen to. An agent choosing for itself
drifts — it finds a topic elegant, writes fifteen hundred words about it, and you discover at
breakfast that you never wanted it. Here the worst case is a proposal you delete in ten seconds.

---

## Honest limitations

* The narration is synthesized. It is good, not human. Say so on the page.
* An agent choosing its own topics will occasionally choose badly. The nightly/morning split
  exists so you can catch that.
* Everything the agent writes should be treated as needing verification. `podcast.py links` catches
  fabricated URLs; it cannot catch a confidently wrong sentence. Read the episodes.
* This publishes to HuggingFace because static Spaces are free and need no server. Any static
  host works; the `hf` step and the `align` workaround in `podcast.py` are the only code that
  knows about HuggingFace.

---

## Licence

MIT. The prompts and lessons are the valuable part — take them.
