# KnowledgePalace interface

Optional. `PALACE_DIR` lets the podcast call KnowledgePalace for literature retrieval, evidence
analysis and paper ingest. KnowledgePalace does not store episodes, scripts, daily or weekly
reports, or a podcast project. The podcast remains fully usable when this interface is disabled.

## Retrieval and analysis

During `prepare`, the agent queries the library with
`python -m knowledge_palace.interaction.research ask ...`: lightly while proposing candidates, to
show what the library already holds on each, and in full during `prepare --write`. When the
listener has queued nothing, the library's open gaps are what the candidates are drawn from. The resulting comparison is saved
only in the podcast episode JSON and rendered on the podcast page under "Against the library".

The comparison may contain:

- `coverage`: whether the library contains direct or adjacent evidence;
- `analysis.adds`, `analysis.differs`, `analysis.relates`: the podcast editor's comparison;
- `analysis.takeaways`: up to five one-sentence take-home points per section, rendered as
  a bullet list beneath that section's prose; optional, and skipped when absent;
- `references`: bibliographic references used by that comparison;
- `ingest`: papers selected for optional library ingest.

These fields are podcast content. They are never copied into a KnowledgePalace project or material
record.

## Optional ingest

After a reviewed episode is published, papers explicitly listed in `palace.ingest` may be sent to
the normal KnowledgePalace ingest workflow. The same operation can be retried with:

```text
python scripts/podcast.py palace episodes/NNN
```

The ingest process resolves identity, reuses existing cards, records honest source coverage and
reading depth, and skips papers outside registered domains. It creates or deepens ordinary paper
cards and their evidence relations. It does not create a `daily-podcast` project, episode material,
report, or podcast-labelled provenance in the library.

Every topic comes from the listener's queue or from the library's open questions — those are the
only two sources — so `prepare --write` stamps `topic_source` as `listener` or `library` in
`episode.json`, and the ingest list is honoured for both.

The retry receipt is stored in the podcast's own `episode.json` as
`knowledge_palace_ingest`. A successful receipt prevents an unnecessary repeat. Weekly issues list
their papers under the same `palace.ingest` key and keep the receipt in the issue's `provenance`,
also inside the podcast project.

## Boundaries

- `PALACE_DIR` may be empty; podcast generation, audio, pages and publication still work. The
  one thing that changes is where topics come from: without the library, `prompts/queue.md` is
  the only source, and a night with an empty queue ends without a proposal.
- KnowledgePalace is responsible for literature identity, reading assets, cards, Claims, Gaps and
  evidence relations.
- The podcast is responsible for topic selection, editorial synthesis, episode and weekly content,
  audio, pages, publication and its own operational records.
- Library queries are read-only. Ingest is the only optional write path from podcast to
  KnowledgePalace.
- The ingest prompt runs inside `PALACE_DIR`, so KnowledgePalace's own workflow and registered
  domains remain authoritative.
