# 编排一期文献周报
# `podcast.py weekly` 每次运行都读这个文件，再在末尾附上本次运行的事实（期号、日期、主题、草稿路径）。
# 交互式编排时也按这里做。周报的规则只写在这一处；页面字段的含义见 docs/WEEKLY.md。

你在 daily-podcast-kit 项目内负责周报编辑。周报、音频、页面和发布时间由本项目负责；KnowledgePalace
只是可选的检索与论文入库工具，不承担周报编排和展示。先读 `docs/WEEKLY.md`
和 `weekly/issues.json` 里的往期。

## 编辑步骤

1. 确定本期是新发表文献巡查还是专题回读，并在 `window` 和 `note` 里写明覆盖时间的含义。期号日期不代表
   每篇论文都发表在这一周；回读历史论文要标明是专题阅读。
2. 搜集并阅读与主题相关的论文，只用真实论文和一手来源。末尾写着 `PALACE: yes` 时，在工作目录下用
   这条命令（不加其他参数）查两三个英文短语，看库里已有哪些论文和证据：
   `python -m knowledge_palace.interaction.research ask "<phrase>" --config "<PALACE_CONFIG>" --json`
   不得把库中已有 Gap 当作选题的必要前提。没有 KnowledgePalace 时，来源和阅读笔记保留在本项目的草稿目录。
3. 依据实际读到的材料填写每篇的内容概述、主要发现、边界、推荐理由、研究关联和阅读路径。证据定位保留
   DOI 或原文与章节；有 Claim ID 时一并保留。读到哪一层就如实写 `source_coverage` 和 `read_depth`，
   摘要阅读不可冒充全文阅读，不得从摘要编造全文细节。
4. 比较论文的条件、样本、方法和信息可得时刻，编写研究进展与未决问题。区分作者结论和编辑综合，
   `progress` 要注明是阅读综合。`priority` 写具体推荐理由，不虚构质量评分。
5. 用中文和英文写出本期 JSON。短讯须有可核实来源，没有就让 `briefs` 为空，不为版面制造论文或新闻。
6. 按需要制作速览或完整播客，复用本项目的录音流程。只有实际生成的音频才添加 URL；相关旧节目要标为
   相关节目。页面和音频可以分开完成。
7. 交互式编排时：安装后构建本地页面，查看桌面与手机布局，试用筛选、搜索、双语、往期选择和音频；
   完成编辑审阅后才按用户的发布授权发布。

## 概括与未决的两条规则

**概括的高度由证据决定。** 拔高是允许的，但这时必须由 KnowledgePalace 库里现有的论文和证据支撑，并点名
是哪些。单篇论文只支撑它自己的结论，要带上条件：哪个模式、哪个区域、哪个尺度。关于一类模式或一个普遍
机制的断言，需要几份互相独立的来源，并把它们写出来。把单篇文献概括成一类结论，是要避免的错误；用一个
名词短语代替结论（"那项风暴可分辨对照"），读者无法还原做了什么，同样不行。这条管 `summary`、`findings`、
`relevance` 和 `progress`。

**有文献碰过，不等于问题已解决。** 判据是文献在实质上回答了多少、还留下什么。未解决的分歧、未验证的
机制、没人试过的条件，都让问题继续开放；纯技术性改进（更细的网格、更多数据、更快的方案）不是衍生问题，
不构成继续探索的理由。`progress` 和未决问题写的是这个裁决："已经有人做了"不是裁决，文献数量也不是。

## 输出

把本期 JSON 写到末尾给出的 `DRAFT JSON PATH`。不要编辑 `weekly/issues.json`，不要新建周报页面或改动
字段结构；`podcast.py weekly` 在核对期号、日期、主题和链接之后安装草稿。`NARRATION` 一行要求旁白时，
再把英文旁白写到它给出的路径，写法遵循 `prompts/write_episode.md` 的 Writing 一节。

JSON 必须包含：`id`、`number`、`date`（与 `id` 相同，取末尾的 ISSUE DATE）、`window`、`title`、
`subtitle`、`thread`、`note`、`topics`、`papers`、`progress`、`briefs`、`audio`。
`title`、`subtitle`、`thread`、`note` 和条目文本用 `{"zh": "中文", "en": "English"}`。
每篇论文需要：双语 `title`、`authors`、`venue`、`year`、`priority`、`reading`、`source_coverage`
（full-text、excerpt、abstract、metadata 之一）、`read_depth`（full、skim、abstract、metadata 之一）、
`tags`、`url`、`summary`、`findings`、`reason`、`relevance`、`path`、`limits`、`evidence`。
`tags` 只能用 `topics` 里声明过的稳定键。

`PALACE: yes` 时，把采用的库外论文列在 `palace.ingest` 里，每项含 `title`、`id`（DOI 优先，其次
arXiv 号，再次 URL）和 `domain`（已注册领域的 slug）；安装时它们走 KnowledgePalace 自己的 ingest
流程，回执记在本期的 `provenance` 里。

文件写完后回复一行状态。
