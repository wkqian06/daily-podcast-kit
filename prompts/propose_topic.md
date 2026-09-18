# PROPOSE — put two or three candidates in front of the listener, then stop
# Runs nightly. You do NOT write the episode here. The listener confirms one first, and
# `podcast.py prepare --write` writes it. Editable.

## Where the topic comes from

1. **The listener named it.** The header below carries `TOPIC (from the listener)`. That subject is
   settled: candidate one is it, taken in the spirit intended. The other candidates are different
   angles on the same subject, or the neighbouring question it points at — never a substitute.
2. **The listener's research library.** Nothing is queued and the header says `PALACE: yes` with a
   list of OPEN GAPS. Choose two or three different open questions, query the library for each
   (command below), and propose one candidate per question. The argument is what the literature
   does and does not settle, and why. Variety here means a different gap and concept cluster from
   the last two episodes, not a different field: the library has few domains, and that is the point.

There is no third source. When neither applies the job stops before calling you, so you will never
be asked to invent a subject to fill the slot.

## Filters, applied to every candidate, in order

0. **Is it inside what they actually work on?** The queue line and the library's domains are the
   evidence of that, and they are the only evidence you have. A topic that is elegant but sits
   outside both is a miss, however good the argument.
1. **Is there an argument?** Not "here is a thing that happened", but a claim worth ten minutes:
   a mechanism worth understanding, a framing worth challenging, a connection nobody draws.
   If you cannot state the argument in one sentence, it is not a candidate.
2. **Can it be pictured?** Prefer topics where a listener can build a mental image: plain language
   and a vivid explanation beat a correct abstraction.
3. **Variety.** Read the `episode.json` of the two most recent `episodes/NNN/` — title, subtitle
   and summary. Do not propose the same domain as either of them.
4. **Can you get it right?** The next section. This is the one the proposal exists for.

Avoid: press-release science, product launches, anything where the honest verdict is "too early to
say", and culture-war material.

## Can you get the text?

A live URL is not a read paper. Before proposing a candidate, try to reach the sources its argument
would rest on. These routes work, all of them with a browser User-Agent:

* **Europe PMC**: `https://www.ebi.ac.uk/europepmc/webservices/rest/<PMCID>/fullTextXML`, with the
  PMCID from `.../rest/search?query=DOI:"<doi>"&format=json&resultType=core`. This reaches PNAS and
  Nature Communications papers whose doi.org links give you a 403.
* **Institutional repositories**: `https://api.openalex.org/works/doi:<doi>`, then every entry in
  `locations[]`, not only `best_oa_location`.
* **Direct publisher PDF** for Springer, Copernicus and arXiv, which do not block.
* **Crossref**, `https://api.crossref.org/works/<doi>`, for title, year, volume and pages.

Two walls do not come down from here: AAAS/Science, and `journals.ametsoc.org`, which blocks
scripts and browsers alike at its CDN. A paper behind one of those is not a dead end at this stage:
list it under that candidate's "原文我拿不到". The listener can drop the PDF into
`materials/NNN/` before confirming, and the writing run reads every file there in full.
Say honestly per candidate what you could open and what you could not; a candidate whose whole
argument sits behind a wall, with nothing the listener could supply, is not worth proposing.

## The listener's research library (only when the header below says PALACE: yes)

The header lists the registered domains, the config path and the open gaps. Query the library with
one or two short English phrases per candidate, from the working directory, with no other flags:

    python -m knowledge_palace.interaction.research ask "<phrase>" --config "<PALACE_CONFIG>" --json

At this stage you only need to know what the library already holds on each candidate, so the
listener can judge whether the episode would repeat what they have read. The full comparison, the
`palace` object and the ingest list all happen in the writing run, not here.

## Two rules, the same ones the writing run applies

**Generality is set by the evidence.** Pitching a claim high is allowed when it is the library's
holdings that carry it, and then the claim names them. One paper carries its own result with its
conditions attached: the model, the region, the scale. A claim about a class — models of a kind, a
mechanism in general — needs several independent sources under it. An argument that rests on one
paper but is stated as if it were about a class is not a candidate: narrow it to what that paper
shows, or find the others before proposing it. This governs the 论点 line and the 库里已有 line.

**Papers on a question do not close it.** Whether a gap is still worth an episode is judged on what
the literature settles in substance and on what it leaves: an unresolved disagreement, an untested
mechanism or a condition nobody has probed keeps it open, while a purely technical improvement — a
finer grid, more data, a faster scheme — is not a derived question and does not keep it open. Do
not drop a library gap because work on it exists, and do not propose one as settled for that
reason either. Under 库里已有, say which of the two it is.

## Output

Write the proposal to the TOPIC FILE path given below, **in Chinese**, exactly this shape, and keep
the `CHOICE:` line as the second line so the tooling can read it:

```
# 选题提案 · 第 NNN 集 · <the date given below>

CHOICE:

把选中的候选编号写在上面那行的冒号后面，也可以直接写你自己的题目。
拿不到的原文放进 materials/NNN/。然后运行：
    python scripts/podcast.py prepare --write

## 候选 1 · <标题，不是题目标签>
- 论点：<一句话，这一集要主张什么>
- 为什么值得十分钟：<一两句>
- 来源：<2-4 条，每条注明 全文已读 / 只有摘要 / 拿不到>
- 原文我拿不到：<列出来，或者写“无”>
- 库里已有：<库里已经覆盖了什么，或者写“无”>        <- 只在 PALACE: yes 时写这一行
- 风险：<什么情况下这会是一集坏节目>

## 候选 2 · ...
## 候选 3 · ...
```

Nothing else: no script, no `episode.json`, no audio, no edits to any other file. The whole point
of this run is that the listener sees the options before ten minutes of narration exist.

When the file is written, print exactly: PROPOSAL_OK followed by the episode number and the number
of candidates.
