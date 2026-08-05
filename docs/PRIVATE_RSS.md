# Private podcast feed — Cloudflare Worker + R2

This gives you an unlisted RSS feed you can subscribe to in any podcast app, so episodes
arrive on your phone and in the car instead of only living on a web page. Audio and
captions sit in R2; a Worker serves the feed and streams the media behind a secret token.

It is optional and independent of the web-page target. You can run either, or both.

---

## Why the Worker serves the audio itself

The obvious design is to hand out storage URLs directly. Do not.

Podcast clients seek, so they issue HTTP Range requests, and some reuse a redirect target
across requests. A pre-signed storage URL bound to one byte range then fails on the second
request, and the player sits on a spinner forever with no error. We hit exactly this on
another host: the same signed URL answered `206` for `bytes=0-1` and **`403`** for
`bytes=2-100000`.

Serving through the Worker keeps one stable URL and lets R2 answer every range. See
`LESSONS.md` §1 for the full postmortem.

---

## Setup

### 1. Enable R2 (one-time, in the browser)

R2 cannot be enabled from the CLI. Go to
`https://dash.cloudflare.com/<ACCOUNT_ID>/r2` and enable it.

**Cloudflare asks for a payment method even for the free tier.** The free allowance is
10 GB of storage and 1 million class-A operations a month; a daily ten-minute podcast is
about 2.5 MB an episode, so under 1 GB a year. You will not be charged, but you cannot
skip the card.

Without this, `wrangler r2 bucket create` fails with `code: 10042`.

### 2. Log in

```bash
cd worker
npm install
npx wrangler login
```

**On a headless machine** the OAuth flow still works, with one manual step. wrangler prints
a `dash.cloudflare.com/oauth2/auth?...` URL and starts listening on `localhost:8976`. Open
the URL in a browser anywhere, approve, and the browser will fail to load
`localhost:8976/oauth/callback?code=...` — that is expected, since that localhost is the
server. Copy the whole failed URL out of the address bar and fetch it on the server:

```bash
curl "http://localhost:8976/oauth/callback?code=...&state=..."
```

wrangler completes the login. The code is single-use and expires in minutes, so passing it
around is far safer than passing an API token.

### 3. Create the bucket

```bash
npx wrangler r2 bucket create private-podcast
```

### 4. Register a workers.dev subdomain

First-time accounts have none, and `wrangler deploy` fails with *"You need to register a
workers.dev subdomain"*. It cannot be done non-interactively, but the API can:

```bash
ACC=<your account id>
TOK=$(grep -oP 'oauth_token\s*=\s*"\K[^"]+' ~/.config/.wrangler/config/default.toml)
curl -X PUT "https://api.cloudflare.com/client/v4/accounts/$ACC/workers/subdomain" \
  -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"subdomain":"your-name"}'
```

Or just click through the dashboard link wrangler prints.

### 5. Set the secrets

```bash
openssl rand -hex 24 | npx wrangler secret put FEED_TOKEN     # appears in the feed URL
openssl rand -hex 24 | npx wrangler secret put UPLOAD_TOKEN   # for publishing
```

Keep copies — you need `FEED_TOKEN` to build the subscription URL and `UPLOAD_TOKEN` in
`config.env`.

### 6. Deploy

```bash
npx wrangler deploy
```

**A brand-new workers.dev subdomain takes about a minute before its TLS certificate is
live.** Until then every request fails with `SSL alert 40 / handshake failure`, which looks
like a configuration error and is not. Poll until it answers:

```bash
until curl -sf https://<worker>.<subdomain>.workers.dev/health; do sleep 30; done
```

### 7. Point the pipeline at it

In `config.env`:

```bash
RSS_BASE="https://private-podcast.<subdomain>.workers.dev"
RSS_UPLOAD_TOKEN="<the UPLOAD_TOKEN you generated>"
```

The nightly and morning jobs pick it up automatically.

### 8. Publish and subscribe

```bash
set -a; source config.env; set +a
UPLOAD_TOKEN="$RSS_UPLOAD_TOKEN" python3 scripts/publish_rss.py \
    --base "$RSS_BASE" --episodes episodes --title "Your Show"
```

Subscribe with:

```
https://private-podcast.<subdomain>.workers.dev/f/<FEED_TOKEN>/feed.xml
```

---

## Gotchas

**Cloudflare's bot protection blocks Python.** The default `Python-urllib/3.x` User-Agent
gets a `403` at the edge, before the request reaches your Worker — while the identical
request from curl succeeds. `publish_rss.py` sends a browser User-Agent for this reason. If
you write your own client, do the same.

**Do not percent-encode the slashes in object keys.** `encodeURIComponent("audio/ep1.m4a")`
produces `audio%2Fep1.m4a`, which our Worker happens to decode but stricter clients refuse.
The Worker encodes each path segment separately.

**The feed URL is the credential.** To revoke access, set a new `FEED_TOKEN`; every old URL
dies immediately and subscribers need the new one. `<itunes:block>Yes</itunes:block>` is set
so well-behaved directories will not index the feed, but that is a request, not enforcement.

---

## Testing without a Cloudflare account

`wrangler dev --local` emulates R2 on disk, so the whole thing can be exercised before you
sign up for anything:

```bash
cd worker
cp .dev.vars.example .dev.vars
npx wrangler dev --local --port 8787 &

cd ..
UPLOAD_TOKEN=localtestuploadtoken python3 scripts/publish_rss.py \
    --base http://127.0.0.1:8787 --episodes episodes
curl -s http://127.0.0.1:8787/f/localtestfeedtoken/feed.xml
```

Worth verifying, in this order:

```bash
B=http://127.0.0.1:8787; T=localtestfeedtoken; U="$B/f/$T/a/audio/ep001.m4a"

curl -s -o /dev/null -w '%{http_code}\n' $B/f/WRONG/feed.xml     # expect 404
curl -s -o /dev/null -w '%{http_code}\n' -X PUT --data x $B/upload/x  # expect 404
curl -s $B/f/$T/feed.xml | xmllint --noout -                     # expect no errors

for R in bytes=0-1 bytes=0-1023 bytes=-500 bytes=0-; do          # expect 206 each
  curl -s -o /dev/null -w "$R -> %{http_code}\n" -H "Range: $R" "$U"
done
curl -s -o /dev/null -w 'oversize -> %{http_code}\n' -H "Range: bytes=999999999-" "$U"  # 416
```

The one that matters most is issuing **several different ranges against the same URL** in
sequence. That is the case that fails on hosts with per-range signed URLs, and it is the
reason this Worker exists.

---

## Which podcast apps show the transcripts

The feed advertises captions with `<podcast:transcript type="text/vtt">`, generated from
the timings measured during synthesis, so they are exact rather than estimated.

Support varies, and not in the way you would guess:

* **Snipd** ignores the RSS transcript tag and generates its own with AI. On the free plan
  that is limited to a couple of episodes a week, so transcripts often simply do not appear —
  for any podcast, not just yours.
* **Podverse**, **Fountain** and other Podcasting 2.0 apps read the tag directly.
* **Apple Podcasts** generates its own transcripts and ignores the tag.

**No third-party app can show a transcript on CarPlay.** Apple's CarPlay templates do not
expose synced text to third-party audio apps, for driver-distraction reasons. iOS 26 added a
widgets page that some apps use for lyrics, but it does not replace the Now Playing screen.
If reading along matters, that happens on the phone or the web page, not in the car.
