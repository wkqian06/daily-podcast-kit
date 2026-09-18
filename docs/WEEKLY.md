# 文献周报

周报由 podcast 项目编排和展示。KnowledgePalace 是可选工具：可检索已有证据、阅读入库与获取 Claim 定位，不负责周报页面或发布。

## 页面与生成

- 用 `python scripts/podcast.py weekly --topic "..."` 生成一期草稿并安装到 `weekly/issues.json`；也可用 `--draft FILE --date YYYY-MM-DD` 安装已审核的 JSON，日期必须与草稿的 `id`/`date` 一致。命令拒绝重复期号、缺少论文和未声明主题，并默认探测论文与短讯链接；`--days N` 改阅读覆盖天数（默认 7），断网时用 `--skip-links` 跳过链接探测。
- 编辑 `weekly/issues.json`：一个数组，每期包含稳定的 `id`、期号、日期、阅读覆盖时间及内容。新一期放在数组前面，历史期保留。草稿保存在 `weekly/drafts/YYYY-MM-DD/`，作为本期来源记录；构建时不会复制进 `site/weekly/`，草稿里的阅读笔记不会随页面发布。
- `weekly/index.html`、`weekly/weekly.css`、`weekly/weekly.js` 是共享页面，不需要每期复制模板。
- `python scripts/podcast.py weekly --topic "强对流环境的环境时空特征分析" --date 2026-09-21` 同时安装 issue 并生成播客首页和 `site/weekly/index.html`。播客首页提供周报入口。
- 本地查看：`python -m http.server 8768 --bind 127.0.0.1 --directory site`，访问 `http://127.0.0.1:8768/weekly/index.html`。
- `#2026-09-14` 可直达指定期；页面提供往期选择、关键词搜索、主题筛选、中英和深色切换。
- 现有 `publish` 流程会携带周报静态目录。`weekly` 和 `build_site.py` 都不会发布；调度仍由 podcast 项目外部配置决定。

## 内容

每期有标题、线索、论文、跨论文进展、短讯和音频；科学内容由阅读与编辑产生，页面仅负责展示。

论文条目包括双语标题、作者、期刊、发表年份、`source_coverage`、`read_depth`、主题标签、摘要、关键发现、推荐理由、研究关联、阅读路径、局限、原文链接与证据定位。当前首期数据可作为字段示例。`priority` 是编辑说明，不是数值质量评分。

`title`、`subtitle`、`thread`、`note` 以及条目的文本使用 `{"zh": "中文", "en": "English"}`。主题用稳定键关联 `topics`。搜索覆盖条目的两种语言和证据标识。

日期描述真实覆盖范围；回读历史论文时明确标注专题阅读，不能称为本周新论文。跨论文推断标为阅读综合。没有可核实资讯时 `briefs` 留空。不要为了版面数量制造论文或新闻。

## 音频

`audio` 是音频区块数组。每项包含双语 `title`、`note`，有录音时添加相对于周报页面的同源 `url`。可分别放速览、完整周报录音；缺少录音时展示说明，没有失效播放器。

相关旧节目须标为相关节目，不冒充本期完整录音。现有节目音频路径为 `../audio/epNNN/episode.m4a`。独立周报录音可保存在 `weekly/audio/`，使用 `audio/filename.m4a`；整目录随构建复制。音频使用完整 GET 后转 Blob 播放，避免 HuggingFace 的分段签名问题。合成录音标明合成语音。
周报音频只走网页；私有 RSS 只收节目，不含周报。

## 编辑流程

使用 `prompts/weekly.md` 编排一期。搜集、阅读与证据核实完成后，`weekly` 命令安装数据并构建页面。首期为已有材料回读，无新增论文。新搜集并采用的论文在启用 KnowledgePalace 时调用其 ingest 流程，保留原始来源与阅读范围；无库时保存到 podcast 的草稿目录。原文内容、编辑综合和用户观察分别归属。

不带 `--audio` 时，页面可以保留相关节目或未录制说明；带 `--audio` 时，命令读取草稿目录的 `script.txt`，沿用 podcast 的 TTS 与分段流程并把音频复制到 `weekly/audio/`。周报的自动每周调度仍需单独配置。
