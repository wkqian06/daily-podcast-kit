# First run

## 1. Install

```bash
pip install -r requirements.txt
```

Kokoro downloads its model on first use, about 330 MB. The Chinese voice, if you enable
translation and want Chinese narration, lives in a separate repository with different weights —
see the notes in `scripts/make_audio.py`.

You also need the `claude` CLI on `PATH`, already authenticated. Check with:

```bash
claude -p "reply with exactly: OK"
```

## 2. Configure

```bash
cp config.env.example config.env
```

Fill in:

* `HF_TOKEN` — a **write** token from <https://huggingface.co/settings/tokens>
* `PODCAST_SPACE` — `your-username/whatever`. The Space is created on first publish.
* `PODCAST_TITLE`, `PODCAST_BLURB` — what the page calls itself
* `TRANSLATE_TO` — leave empty unless you want a second-language transcript

`config.env` is gitignored. Keep it that way: it holds a token that can write to your account.

## 3. Set up the taste file

```bash
cp prompts/taste.example.md prompts/taste.md
```

Edit it to describe who is listening. It will be mostly empty at first. That is fine — it fills
in as you react to episodes, and that is what makes topic selection improve. See the note in
`README.md` about why this file matters more than it looks.

## 4. Produce the example episode

This exercises the whole pipeline without publishing anything.

```bash
set -a; source config.env; set +a
E=episodes/001-example

python3 scripts/check_links.py $E
python3 -c "import json;s=open('$E/script.txt').read();\
json.dump({'podcast':' '.join(s.split())},open('$E/narration.json','w'))"
python3 scripts/make_audio.py $E/narration.json $E
python3 scripts/build_site.py site
python3 scripts/align_utf8.py site/index.html
```

Open `site/index.html` in a browser. You should see the episode, a player, and a transcript that
highlights as it plays.

**Sanity check the duration.** It should be roughly `words / 150` minutes. If it is far shorter,
read `LESSONS.md` §3.

## 5. Publish

```bash
python3 scripts/publish_hf.py site
```

It prints three URLs. Open the `SITE_URL` one. Give it a minute — a new Space takes a moment to
build the first time.

**Then check it on a phone.** This is not optional; the failure mode in `LESSONS.md` §1 is
invisible on desktop and total on iOS.

## 6. Schedule it

```bash
crontab -e
```

```cron
# Choose and produce tomorrow's episode, leaving a window to veto it
0 22 * * * /path/to/daily-podcast-kit/scripts/prepare_episode.sh >> /path/to/daily-podcast-kit/logs/cron.log 2>&1
# Publish whatever is ready
0 7 * * *  /path/to/daily-podcast-kit/scripts/daily_publish.sh  >> /path/to/daily-podcast-kit/logs/cron.log 2>&1
```

Use absolute paths. cron runs with a minimal `PATH`; both scripts prepend the usual interpreter
locations, but if your Python or `claude` lives somewhere unusual, add it there.

Times are your machine's local time. Check with `timedatectl`.

## 7. First week

Read every episode before it goes out — that is what the nightly/morning gap is for. When you
react to one, write the reaction into `prompts/taste.md`, including the times the agent guessed
wrong. After a week or two it will be choosing topics you actually want.

## Troubleshooting

| problem | check |
|---|---|
| `KeyError: 'HF_TOKEN'` | you did not `source config.env` |
| `402 Payment Required` on publish | you are creating a Gradio/Docker Space; this must be `static` |
| audio much shorter than expected | `LESSONS.md` §3 |
| a character shows as `�` online but not locally | `LESSONS.md` §2 — did `align_utf8.py` run last? |
| audio stalls on iPhone, fine on desktop | `LESSONS.md` §1 |
| cron job silently does nothing | check `logs/`; usually `PATH` or a relative path |
