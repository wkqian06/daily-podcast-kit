#!/usr/bin/env python3
"""Build the podcast site from podcast/episodes/*/ into one page.

Every episode lives in its own folder (episode.json, script.txt, audio/) but they all
render into a single index.html and a single HuggingFace Space — new episodes are
appended, nothing is replaced.

Three things the page does beyond playing audio:
  * the transcript highlights in step with the audio and auto-scrolls, using the EXACT
    per-sentence timings emitted by make_audio.py (Kokoro synthesizes sentence by
    sentence, so these are measured, not estimated);
  * clicking any sentence seeks the audio to it;
  * each episode ends with comprehension questions whose answers are hidden until asked for.

Audio follows the same rule as the weekly digest, and for the same reason: HuggingFace
signs each CDN URL for ONE byte range, so a media element that range-requests a Space
file stalls forever on iOS Safari. Small files are inlined as data: URIs; anything
larger gets a button that fetches the whole file once and plays it from a blob.

Usage: build_podcast.py [output_dir]     (default: podcast/site)
"""
import base64
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EPISODES = os.path.join(ROOT, "episodes")
INLINE_LIMIT = 700_000

SPACE = os.environ.get("PODCAST_SPACE", "your-username/daily-podcast")
DISCUSS = f"https://huggingface.co/spaces/{SPACE}/discussions"

CSS = """
*{box-sizing:border-box}
:root{color-scheme:light dark;
  --bg:#f7f8fa;--panel:#fff;--ink:#12151c;--muted:#5b6472;--line:#e3e7ee;
  --brand:#3f5bd9;--hi:#fff3c4;--hi-ink:#3d2f00;--shadow:0 1px 2px rgba(16,24,40,.05)}
@media (prefers-color-scheme:dark){:root{
  --bg:#0f1218;--panel:#161b24;--ink:#e8ecf3;--muted:#95a0b1;--line:#252c38;
  --brand:#8ea2ff;--hi:#3b3a1f;--hi-ink:#ffe9a3;--shadow:none}}
body{margin:0;background:var(--bg);color:var(--ink);line-height:1.65;
  font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:0 18px}
h1{font-size:26px;line-height:1.25;margin:0 0 6px;letter-spacing:-.01em}
.tagline{color:var(--muted);font-size:14px;margin:0 0 18px}

/* top bar: menu, title, prev/next */
.bar{position:sticky;top:0;z-index:40;display:flex;align-items:center;gap:10px;
  padding:10px 14px;background:var(--panel);border-bottom:1px solid var(--line)}
.bar .brand{font-weight:800;font-size:15px;letter-spacing:-.01em;flex:1 1 auto;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bar button{border:1px solid var(--line);background:transparent;color:var(--ink);
  font:inherit;font-size:15px;line-height:1;border-radius:9px;padding:7px 11px;cursor:pointer}
.bar button:hover:not([disabled]){border-color:var(--brand);color:var(--brand)}
.bar button[disabled]{opacity:.35;cursor:default}
.bar .count{font-size:12.5px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}

/* left drawer, closed by default */
.scrim{position:fixed;inset:0;background:rgba(8,11,16,.45);opacity:0;visibility:hidden;
  transition:opacity .2s;z-index:45}
.scrim.open{opacity:1;visibility:visible}
.drawer{position:fixed;top:0;left:0;bottom:0;width:min(310px,84vw);z-index:50;
  background:var(--panel);border-right:1px solid var(--line);
  transform:translateX(-102%);transition:transform .22s ease;overflow-y:auto;
  padding:16px 14px 30px}
.drawer.open{transform:none}
.drawer .series{font-size:16px;font-weight:800;margin:2px 0 6px;letter-spacing:-.01em}
.drawer .blurb{font-size:12.5px;color:var(--muted);line-height:1.5;margin:0 0 16px}
.drawer h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);
  margin:2px 0 12px;padding-top:12px;border-top:1px solid var(--line)}
.drawer ol{list-style:none;margin:0;padding:0}
.drawer li{margin:0 0 6px}
.drawer a{display:block;padding:9px 11px;border-radius:10px;text-decoration:none;color:var(--ink);
  border:1px solid transparent}
.drawer a:hover{background:var(--bg)}
.drawer a.current{border-color:var(--brand);background:var(--bg)}
.drawer .n{display:block;font-size:11px;font-weight:800;letter-spacing:.05em;color:var(--brand)}
.drawer .t{display:block;font-size:14px;font-weight:600;line-height:1.35;margin-top:3px}
.drawer .d{display:block;font-size:12px;color:var(--muted);margin-top:3px}

/* one episode at a time */
.ep{display:none}
.ep.current{display:block}
.ep.current{background:var(--panel);border:1px solid var(--line);border-radius:16px;
  padding:20px 22px;margin:18px 0 22px;box-shadow:var(--shadow)}
.ep-num{display:inline-block;font-size:11.5px;font-weight:800;letter-spacing:.06em;
  text-transform:uppercase;color:var(--brand);margin-bottom:6px}
.ep h2{font-size:20px;margin:0 0 4px;line-height:1.3}
.ep .sub{color:var(--muted);font-size:14px;margin:0 0 2px}
.ep .when{color:var(--muted);font-size:12.5px;margin:0 0 14px}
.ep .summary{margin:0 0 16px}
.player{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
  border:1px solid var(--line);border-radius:12px;padding:10px 13px;background:var(--bg)}
.player audio{flex:1 1 260px;min-width:200px;height:36px;max-width:100%}
.player .p-label{font-size:12.5px;font-weight:600;color:var(--muted);white-space:nowrap}
.player button{flex:0 0 auto;border:1px solid var(--line);background:transparent;color:var(--ink);
  font:inherit;font-size:12.5px;font-weight:600;border-radius:8px;padding:6px 12px;cursor:pointer}
.player button:hover{border-color:var(--brand)}
.player button[disabled]{opacity:.6;cursor:default}
.player a.dl{flex:0 0 auto;font-size:15px;text-decoration:none;opacity:.55}
.player a.dl:hover{opacity:1}
details{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}
details summary{cursor:pointer;font-weight:700;font-size:14px;list-style:none}
details summary::-webkit-details-marker{display:none}
details summary::before{content:"▸ ";color:var(--brand)}
details[open] summary::before{content:"▾ "}
.hint{font-size:12.5px;color:var(--muted);margin:6px 0 10px;font-weight:400}
.transcript{max-height:60vh;overflow-y:auto;padding-right:6px}
.transcript p{margin:.85em 0}
/* Transcript language. English shows by default; body.zh swaps every segment at once,
   and the timing lives on .seg, so highlight and click-to-seek are unaffected. */
.seg .t-zh{display:none}
body.zh .seg .t-en{display:none}
body.zh .seg .t-zh{display:inline}
body.zh .transcript{line-height:1.85}
.tlang{float:right;display:flex;gap:4px}
.tlang button{border:1px solid var(--line);background:transparent;color:var(--muted);
  font:inherit;font-size:11.5px;font-weight:700;border-radius:7px;padding:3px 9px;cursor:pointer}
.tlang button.on{border-color:var(--brand);color:var(--brand)}
.seg{cursor:pointer;border-radius:4px;padding:1px 2px;transition:background .15s}
.seg:hover{background:rgba(63,91,217,.10)}
.seg.on{background:var(--hi);color:var(--hi-ink)}
.quiz{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}
.quiz h3{font-size:14px;margin:0 0 4px}
.qa{border:1px solid var(--line);border-radius:10px;padding:11px 13px;margin:10px 0;
  background:var(--bg)}
.qa .q{font-weight:600;font-size:14.5px;margin:0}
.qa button{margin-top:9px;border:1px solid var(--line);background:transparent;color:var(--brand);
  font:inherit;font-size:12.5px;font-weight:700;border-radius:8px;padding:5px 11px;cursor:pointer}
.qa button:hover{border-color:var(--brand)}
.qa .a{display:none;margin:10px 0 0;font-size:14px;color:var(--ink);
  border-left:3px solid var(--brand);padding-left:11px}
.qa.open .a{display:block}
.qa.open button{display:none}
.reading{margin-top:16px;border-top:1px solid var(--line);padding-top:12px}
.reading h3{font-size:14px;margin:0 0 8px}
.reading ol{margin:0;padding-left:20px}
.reading li{margin:.5em 0;font-size:14px}
.reading a{color:var(--brand);font-weight:600}
.reading .note{color:var(--muted);font-size:13px;display:block}
footer{margin:26px 0 60px;padding-top:14px;border-top:1px solid var(--line);
  font-size:12.5px;color:var(--muted)}
footer a{color:var(--brand);font-weight:600}
@media (max-width:560px){.player .p-label{flex:1 0 100%} .player audio{width:100%}}
"""

JS = """
(function(){
  // Load-on-demand audio: one plain GET, played from a blob. Never range requests.
  document.querySelectorAll('[data-fetch]').forEach(function(btn){
    btn.addEventListener('click', function(){
      var au=document.getElementById(btn.getAttribute('data-for'));
      if(!au||btn.disabled) return;
      var label=btn.textContent;
      btn.disabled=true; btn.textContent='Loading\\u2026';
      fetch(btn.getAttribute('data-fetch'))
        .then(function(r){ if(!r.ok) throw new Error(r.status); return r.blob(); })
        .then(function(b){
          au.src=URL.createObjectURL(b); au.style.display=''; btn.remove();
          au.play().catch(function(){});
        })
        .catch(function(){ btn.disabled=false; btn.textContent=label; au.style.display=''; });
    });
  });

  // Transcript follows the audio, and clicking a sentence seeks to it.
  document.querySelectorAll('.transcript').forEach(function(box){
    var au=document.getElementById(box.getAttribute('data-for'));
    if(!au) return;
    var segs=[].slice.call(box.querySelectorAll('.seg'));
    if(!segs.length) return;
    var starts=segs.map(function(s){ return parseFloat(s.getAttribute('data-s')); });
    var current=-1, userScrolled=0;

    box.addEventListener('scroll', function(){ userScrolled=Date.now(); });

    segs.forEach(function(s){
      s.addEventListener('click', function(){
        au.currentTime=parseFloat(s.getAttribute('data-s'));
        if(au.paused && au.src) au.play().catch(function(){});
      });
    });

    function find(t){                       // binary search over sentence starts
      var lo=0, hi=starts.length-1, ans=-1;
      while(lo<=hi){ var mid=(lo+hi)>>1;
        if(starts[mid]<=t){ ans=mid; lo=mid+1; } else { hi=mid-1; } }
      return ans;
    }
    au.addEventListener('timeupdate', function(){
      var i=find(au.currentTime);
      if(i===current) return;
      if(current>=0) segs[current].classList.remove('on');
      current=i;
      if(i<0) return;
      var el=segs[i];
      el.classList.add('on');
      // Keep the highlight in view, but yield to a reader who is scrolling themselves.
      if(Date.now()-userScrolled < 4000) return;
      var br=box.getBoundingClientRect(), er=el.getBoundingClientRect();
      if(er.top < br.top+8 || er.bottom > br.bottom-8){
        box.scrollTop += (er.top-br.top) - box.clientHeight*0.35;
      }
    });
  });

  // Comprehension questions: answers stay hidden until asked for.
  document.querySelectorAll('.qa button').forEach(function(btn){
    btn.addEventListener('click', function(){ btn.closest('.qa').classList.add('open'); });
  });

  // ---- Transcript language: a single preference across every episode, remembered.
  function setLang(l){
    document.body.classList.toggle('zh', l === 'zh');
    document.querySelectorAll('.tlang button').forEach(function(b){
      b.classList.toggle('on', b.getAttribute('data-lang') === l);
    });
    try { localStorage.setItem('tlang', l); } catch(e) {}
  }
  document.querySelectorAll('.tlang button').forEach(function(b){
    b.addEventListener('click', function(){ setLang(b.getAttribute('data-lang')); });
  });
  var saved='en';
  try { saved = localStorage.getItem('tlang') || 'en'; } catch(e) {}
  setLang(saved);

  // ---- Deck: one episode at a time, prev/next, and a drawer that starts closed.
  var eps=[].slice.call(document.querySelectorAll('.ep'));
  if(!eps.length) return;
  var drawer=document.getElementById('drawer'), scrim=document.getElementById('scrim'),
      prev=document.getElementById('prev'), next=document.getElementById('next'),
      count=document.getElementById('count'), brand=document.getElementById('brand'),
      links=[].slice.call(document.querySelectorAll('.drawer a')), idx=-1;

  function closeDrawer(){ drawer.classList.remove('open'); scrim.classList.remove('open'); }

  function show(i, push){
    i=Math.max(0, Math.min(eps.length-1, i));
    if(i===idx) return;
    // Leaving a slide stops its audio; otherwise you would hear an episode you can no
    // longer see, and its transcript would keep scrolling off-screen.
    document.querySelectorAll('audio').forEach(function(a){ a.pause(); });
    eps.forEach(function(e,k){ e.classList.toggle('current', k===i); });
    links.forEach(function(a,k){ a.classList.toggle('current', k===i); });
    idx=i;
    prev.disabled = (i===0);            // index 0 is the newest episode
    next.disabled = (i===eps.length-1);
    count.textContent=(i+1)+' / '+eps.length;
    var t=eps[i].getAttribute('data-title')||'';
    brand.textContent=t;
    if(push) history.replaceState(null,'','#'+eps[i].getAttribute('data-slug'));
    window.scrollTo({top:0,behavior:'auto'});
  }

  document.getElementById('menu').addEventListener('click', function(){
    var open=drawer.classList.toggle('open'); scrim.classList.toggle('open', open);
  });
  scrim.addEventListener('click', closeDrawer);
  prev.addEventListener('click', function(){ show(idx-1,true); });   // newer
  next.addEventListener('click', function(){ show(idx+1,true); });   // older
  links.forEach(function(a,k){
    a.addEventListener('click', function(e){ e.preventDefault(); show(k,true); closeDrawer(); });
  });
  document.addEventListener('keydown', function(e){
    if(e.target.matches('input,textarea')) return;
    if(e.key==='ArrowLeft') show(idx-1,true);
    if(e.key==='ArrowRight') show(idx+1,true);
    if(e.key==='Escape') closeDrawer();
  });

  // Deep link if present, else the newest episode.
  var want=(location.hash||'').replace('#','');
  var start=0;
  eps.forEach(function(e,k){ if(e.getAttribute('data-slug')===want) start=k; });
  idx=-1; show(start,false);
})();
"""


def esc(s):
    return html.escape(s or "", quote=True)


def paragraphs(text):
    return [" ".join(p.split()) for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def load_episodes():
    eps = []
    if not os.path.isdir(EPISODES):
        return eps
    for name in sorted(os.listdir(EPISODES)):
        d = os.path.join(EPISODES, name)
        meta_path = os.path.join(d, "episode.json")
        if not os.path.isfile(meta_path):
            continue
        meta = json.load(open(meta_path, encoding="utf-8"))
        meta["_dir"] = d
        sp = os.path.join(d, "script.txt")
        meta["_script"] = open(sp, encoding="utf-8").read() if os.path.exists(sp) else ""
        meta["_audio"] = next(
            (os.path.join(d, "audio", "podcast-en" + e)
             for e in (".m4a", ".mp3")
             if os.path.exists(os.path.join(d, "audio", "podcast-en" + e))), None)
        dur = os.path.join(d, "audio", "durations.json")
        meta["_secs"] = json.load(open(dur)).get("podcast", 0) if os.path.exists(dur) else 0
        seg = os.path.join(d, "audio", "segments.json")
        meta["_segs"] = json.load(open(seg, encoding="utf-8")) if os.path.exists(seg) else []
        zh = os.path.join(d, "audio", "segments_zh.json")
        meta["_zh"] = json.load(open(zh, encoding="utf-8")) if os.path.exists(zh) else []
        if len(meta["_zh"]) != len(meta["_segs"]):
            meta["_zh"] = []          # misaligned translation is worse than none
        eps.append(meta)
    eps.sort(key=lambda e: e.get("number", 0), reverse=True)
    return eps


def transcript_html(ep, aid):
    """Lay the timed segments back into the script's paragraphs.

    A segment can straddle a paragraph break (the narration is synthesized from the
    script with the paragraph breaks collapsed), so matching paragraph text against
    segment text exactly fails. Instead: walk the segments, count the characters
    consumed, and close a paragraph once we have passed that paragraph's length. The
    break can land a sentence early or late; nobody can tell, and every sentence keeps
    its timestamp.
    """
    segs = ep["_segs"]
    if not segs:
        return "".join(f"<p>{esc(p)}</p>" for p in paragraphs(ep["_script"]))

    paras = paragraphs(ep["_script"])
    bounds, run = [], 0
    for para in paras:
        run += len(re.sub(r"\s+", "", para))
        bounds.append(run)

    zh = ep.get("_zh") or []
    out, buf, consumed, b = [], [], 0, 0
    for k, seg in enumerate(segs):
        inner = f'<span class="t-en">{esc(seg["text"])}</span>'
        if zh:
            inner += f'<span class="t-zh">{esc(zh[k])}</span>'
        buf.append(f'<span class="seg" data-s="{seg["start"]}">{inner}</span>')
        consumed += len(re.sub(r"\s+", "", seg["text"]))
        while b < len(bounds) and consumed >= bounds[b]:
            b += 1
            if buf:
                out.append("<p>" + " ".join(buf) + "</p>")
                buf = []
            break
    if buf:
        out.append("<p>" + " ".join(buf) + "</p>")
    return "".join(out)


def player_html(ep, out_dir, aid):
    src = ep["_audio"]
    if not src:
        return '<p class="sub">Audio for this episode is not available yet.</p>'
    num = ep["number"]
    rel_dir = f"audio/ep{num:03d}"
    os.makedirs(os.path.join(out_dir, rel_dir), exist_ok=True)
    published = []
    for ext in (".m4a", ".mp3"):
        cand = os.path.join(ep["_dir"], "audio", "podcast-en" + ext)
        if os.path.exists(cand):
            dst = os.path.join(out_dir, rel_dir, "episode" + ext)
            with open(cand, "rb") as a, open(dst, "wb") as b:
                b.write(a.read())
            published.append(f"{rel_dir}/episode{ext}")
    primary, fallback = published[0], published[-1]
    size = os.path.getsize(os.path.join(out_dir, primary))
    secs = ep["_secs"]
    length = f"{int(secs)//60}:{int(secs)%60:02d}" if secs else ""

    if size <= INLINE_LIMIT:
        mime = "audio/mp4" if primary.endswith(".m4a") else "audio/mpeg"
        with open(os.path.join(out_dir, primary), "rb") as f:
            data = base64.b64encode(f.read()).decode("ascii")
        audio = f'<audio id="{aid}" controls preload="none" src="data:{mime};base64,{data}"></audio>'
        button = ""
    else:
        audio = f'<audio id="{aid}" controls preload="none" style="display:none"></audio>'
        button = (f'<button type="button" data-fetch="{primary}" data-for="{aid}">'
                  f'▶ Load audio ({size / 1048576:.1f} MB)</button>')

    return ('<div class="player">'
            f'<span class="p-label">🎙 Listen{("  ·  " + length) if length else ""}</span>'
            f'{audio}{button}'
            f'<a class="dl" href="{fallback}" download target="_blank" rel="noopener" '
            f'title="Download" aria-label="Download">⤓</a></div>')


def episode_html(ep, out_dir):
    aid = f'au{ep["number"]:03d}'
    slug = f'{ep["number"]:03d}'
    parts = [f'<article class="ep" data-slug="{slug}" '
             f'data-title="{esc(ep["title"])}">',
             f'<span class="ep-num">Episode {slug}</span>',
             f'<h2>{esc(ep["title"])}</h2>']
    if ep.get("subtitle"):
        parts.append(f'<p class="sub">{esc(ep["subtitle"])}</p>')
    parts.append(f'<p class="when">{esc(ep.get("date",""))}</p>')
    if ep.get("summary"):
        parts.append(f'<p class="summary">{esc(ep["summary"])}</p>')
    parts.append(player_html(ep, out_dir, aid))

    if ep["_script"]:
        parts.append(
            '<details open><summary>Transcript</summary>'
            + (('<div class="tlang"><button type="button" data-lang="en">EN</button>'
                '<button type="button" data-lang="zh">中文</button></div>')
               if ep.get("_zh") else "")
            + '<p class="hint">Follows the audio as it plays — tap any sentence to jump there.</p>'
            f'<div class="transcript" data-for="{aid}">{transcript_html(ep, aid)}</div></details>')

    if ep.get("quiz"):
        qs = "".join(
            f'<div class="qa"><p class="q">{i+1}. {esc(q["q"])}</p>'
            f'<button type="button">Show answer</button>'
            f'<p class="a">{esc(q["a"])}</p></div>'
            for i, q in enumerate(ep["quiz"]))
        parts.append('<div class="quiz"><h3>Check your understanding</h3>'
                     '<p class="hint">Try answering before revealing — these are the points '
                     'the episode turns on.</p>' + qs + '</div>')

    if ep.get("further_reading"):
        items = ""
        for r in ep["further_reading"]:
            note = f'<span class="note">{esc(r["note"])}</span>' if r.get("note") else ""
            items += (f'<li><a href="{esc(r["url"])}" target="_blank" rel="noopener">'
                      f'{esc(r["title"])}</a>{note}</li>')
        parts.append(f'<div class="reading"><h3>Further reading</h3><ol>{items}</ol></div>')

    parts.append("</article>")
    return "".join(parts)


def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    eps = load_episodes()
    body = "".join(episode_html(e, out_dir) for e in eps) or "<p>No episodes yet.</p>"
    menu = "".join(
        f'<li><a href="#{e["number"]:03d}"><span class="n">EP {e["number"]:03d}</span>'
        f'<span class="t">{esc(e["title"])}</span>'
        f'<span class="d">{esc(e.get("date",""))}</span></a></li>'
        for e in eps)
    TITLE = os.environ.get("PODCAST_TITLE", "The Daily Ten")
    BLURB = os.environ.get("PODCAST_BLURB",
        "Ten minutes on one thing worth understanding. A paper read closely, a story worth "
        "telling, an argument worth having. Anything is fair game.")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<base target="_blank">
<title>{TITLE}</title>
<style>{CSS}</style>
</head>
<body>
<div class="bar">
  <button id="menu" type="button" aria-label="All episodes" title="All episodes">☰</button>
  <span class="brand" id="brand"></span>
  <span class="count" id="count"></span>
  <button id="prev" type="button" aria-label="Newer episode" title="Newer (←)">‹</button>
  <button id="next" type="button" aria-label="Older episode" title="Older (→)">›</button>
</div>
<div class="scrim" id="scrim"></div>
<nav class="drawer" id="drawer">
  <p class="series">🎙 {TITLE}</p>
  <p class="blurb">{BLURB}</p>
  <h2>All episodes</h2>
  <ol>{menu}</ol>
</nav>
<div class="wrap">
{body}
<footer>
  <p>Want a topic covered, or a paper read closely?
     <a href="{DISCUSS}">Leave a note on the Community tab</a> — it decides what gets made next.</p>
  <p>Narration is synthesized. Factual claims link to their sources above; where reporting is
     contested or incomplete, the episode says so.</p>
</footer>
</div>
<script>{JS}</script>
</body>
</html>
"""
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page)
    print(f"build_podcast: {len(eps)} episode(s) -> {out_dir}/index.html "
          f"({os.path.getsize(os.path.join(out_dir, 'index.html'))/1024:.0f} KB)")
    return out_dir


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "site"))
