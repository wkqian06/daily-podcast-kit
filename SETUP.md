# First run

## 1. Install

```bash
pip install -r requirements.txt
```

Kokoro downloads its model on first use, about 330 MB, into the HuggingFace cache
(`~/.cache/huggingface`). On Windows, use a virtualenv outside OneDrive — see `docs/WINDOWS.md`.

You also need the `claude` CLI on `PATH`, already authenticated. Check with:

```bash
claude -p "reply with exactly: OK"
```

## 2. Choose your delivery targets

Both are optional; configure at least one.

* **Web page** — a public page with the synced transcript. Follow `docs/WEB_PAGE.md`.
* **Private podcast feed** — subscribe in any podcast app. Follow `docs/PRIVATE_RSS.md`.

The setup for each lives in its own doc because each has its own account, its own tokens and
its own first-run friction. Come back here when you have the values.

## 3. Configure

```bash
cp config.env.example config.env
```

Fill in:

* `HF_TOKEN` — a **write** token from <https://huggingface.co/settings/tokens>
* `PODCAST_SPACE` — `your-username/whatever`. The Space is created on first publish.
* `PODCAST_TITLE`, `PODCAST_BLURB` — what the page calls itself
* `TRANSLATE_TO` — leave empty unless you want a second-language transcript
* `RSS_BASE`, `RSS_UPLOAD_TOKEN` — only for the private feed; `docs/PRIVATE_RSS.md` fills these in
* `PALACE_DIR` — optional KnowledgePalace checkout for retrieval and paper ingest; empty disables
  the whole interface and nothing else changes. `docs/PALACE.md`
* `CLAUDE_MODEL`, `CLAUDE_EFFORT` — which model writes the episodes. Empty means the `claude` CLI's
  own default, from `~/.claude/settings.json`

`config.env` is gitignored. Keep it that way: it holds a token that can write to your account.

## 4. Produce the first episode

Put a topic on the first line of `prompts/queue.md`, then run the nightly job once by hand. It
proposes two or three candidates and stops:

```bash
python scripts/podcast.py prepare
```

Open `episodes/001/topic.md`, write your pick after `CHOICE:` (a candidate number, or your own
wording), and if the proposal names a paper it could not reach, drop that PDF into
`materials/001/`. Then write it, and build the page locally without publishing anything:

```bash
python scripts/podcast.py prepare --write
python scripts/build_site.py site
python scripts/podcast.py align site/index.html
```

Every command reads `config.env` itself; nothing needs to be sourced first.

Open `site/index.html` in a browser. You should see the episode, a player, and a transcript that
highlights as it plays.

**Sanity check the duration.** It should be roughly `words / 150` minutes. If it is far shorter,
read `LESSONS.md` §3.

## 5. Publish

```bash
python scripts/podcast.py publish     # publishes to whichever targets are configured
```

`publish` refuses to run within an hour of `prepare` finishing: a scheduler catching up after the
machine slept would otherwise ship an episode nobody read. Once you have read it, `publish --now`.

For the web page it prints a `SITE_URL`; give a brand-new Space a minute to build. For the
feed, subscribe with `https://<worker>/f/<FEED_TOKEN>/feed.xml`.

**Then check it on a phone.** This is not optional; the failure mode in `LESSONS.md` §1 is
invisible on desktop and total on iOS.

## 6. Schedule it

```bash
crontab -e
```

```cron
# Propose tomorrow's candidates. It never writes an episode, so it is safe to run unattended
0 22 * * * cd /path/to/daily-podcast-kit && /path/to/python scripts/podcast.py prepare
# Publish whatever is ready
0 7 * * *  cd /path/to/daily-podcast-kit && /path/to/python scripts/podcast.py publish
```

`prepare --write` is deliberately not scheduled: it is the step that turns your confirmation into
ten minutes of narration, and it runs when you have confirmed, not on a clock.

Use absolute paths for the interpreter: cron runs with a minimal `PATH`, and `claude` must be on
it too. Each run appends to `logs/<job>_<date>.log`. Times are the machine's local time.

On Windows, use Claude routines or Task Scheduler instead — `docs/WINDOWS.md`.

For a literature issue, run the podcast-owned weekly command before publishing:

```bash
python scripts/podcast.py weekly --topic "the week's research topic" --date 2026-09-21 --audio
python scripts/podcast.py publish --now
```

The weekly command leaves its draft under `weekly/drafts/`, installs a new archive entry only
after the mechanical checks pass, and rebuilds the same static Space. Review the issue before
publishing it. With `PALACE_DIR` configured, papers listed in `palace.ingest` are sent
through the library's existing ingest workflow during this command. The episode and weekly issue
remain in the podcast project; no podcast project or material is created in KnowledgePalace.

## 7. First week

Read the proposal before you confirm, and the episode before it goes out — that is what the two
gates are for. A proposal you would
not listen to costs you one deleted directory; an episode you would not listen to costs ten
minutes of synthesis and a page you have to clean up.

## Troubleshooting

| problem | check |
|---|---|
| `KeyError: 'HF_TOKEN'` | `config.env` is missing, or `HF_TOKEN` is empty |
| `402 Payment Required` on publish | you are creating a Gradio/Docker Space; this must be `static` |
| audio much shorter than expected | `LESSONS.md` §3 |
| a character shows as `�` online but not locally | `LESSONS.md` §2 — did `podcast.py align` run last? |
| audio stalls on iPhone, fine on desktop | `LESSONS.md` §1 |
| cron job silently does nothing | check `logs/`; usually `PATH` or a relative path |
