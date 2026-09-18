# 在 Windows 上把它跑成 routine

这份文档只讲 Windows 上怎么装、怎么配 HuggingFace、怎么把两个任务挂成定时任务。
流程本身（写稿、合成、发布）见 `CLAUDE.md`；踩过的坑见 `LESSONS.md`。

整个流程都在同一个文件里：两个定时任务，中间夹着一个只有你能做的确认。

```
晚上 22:00   python scripts/podcast.py prepare          出 2–3 个选题候选写进 topic.md，停下。
你确认        episodes/NNN/topic.md 的 CHOICE: 行        拿不到的原文 PDF 放进 materials/NNN/
确认之后      python scripts/podcast.py prepare --write  写稿、核对引用、合成音频、翻译。不发布。
早上 09:00   python scripts/podcast.py publish          生成页面、上传 HuggingFace（和/或私有 RSS）、确认能打开。
```

没确认就不会有稿子：夜间任务无人值守跑一周，也只会把提案重新打印给你看。写完稿到早上发布之间
仍然是审稿窗口，稿子在 `episodes/NNN/script.txt`，可以改、可以删。

---

## 1. 一次性安装

### 1.1 虚拟环境：仓库根目录下的 `.venv`，用 uv 建

`.venv/` 在 gitignore 里。它在 OneDrive 之内，约 4.9 GB、2.6 万个文件，OneDrive 会同步它们；
不想同步就在 OneDrive 设置里把 `.venv` 文件夹排除。在仓库目录下执行：

```bat
cd /d "E:\OneDrive\Agentic AI\daily-podcast-kit"
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe "torch==2.5.1" --index https://download.pytorch.org/whl/cu124
uv pip install --python .venv\Scripts\python.exe -r requirements.txt
```

为什么这样装：

* **不用 Anaconda 自带的环境。** 它里面是 CPU 版 torch 2.1 和 huggingface_hub 0.15，装 kokoro 会把半个 base 环境升级掉。
* **Python 3.12。** torch 2.5.1 没有 3.13 以上的 wheel；uv 会自动下载或复用它管理的 3.12。
* **torch 固定 2.5.1，先装。** 这台机器上默认装到的新版 torch 加载 `c10.dll` 时报 `WinError 1114`，2.5.1 正常（2026-09-13 实测）。
  先装它，之后 `requirements.txt` 里的 kokoro 就不会再拉一个别的版本。
  `cu124` 是给 RTX 4090 用的 CUDA 版，wheel 约 2.5 GB，下载要十几分钟；只想用 CPU 就把 `--index` 换成
  `https://download.pytorch.org/whl/cpu`，十分钟的音频 CPU 合成大约要几分钟，GPU 半分钟。
* **不需要装 ffmpeg。** `imageio-ffmpeg` 自带。
* **不需要 python3、bash、cron。** 所有 `.sh` 已改成 Python，命令里一律用 `python`。

验证：

```bat
.venv\Scripts\python.exe -c "import torch,kokoro;print(torch.__version__, torch.cuda.is_available())"
```

期望看到 `2.5.1+cu124 True`。第一次合成音频时 Kokoro 会下载约 330 MB 模型到 `C:\Users\<你>\.cache\huggingface\hub`。
想换地方，在 `config.env` 里加一行 `HF_HOME="D:\hf-cache"`。

### 1.2 claude 命令行

`podcast.py` 的选题写稿和翻译都是用 `claude -p` 完成的。检查它能用：

```bat
claude -p "reply with exactly: OK"
```

这台机器上已经登录好（2.1.263）。写稿用哪个模型由 `config.env` 的 `CLAUDE_MODEL` 和 `CLAUDE_EFFORT` 决定；
两个都留空才回落到 `~/.claude/settings.json` 里的 `model`。

### 1.3 OneDrive 的两个注意点

* 生成物（`episodes/*/audio/`、`site/`、`logs/`、`.published`）都在 gitignore 里，但 OneDrive 照样同步。每集约 2.5 MB，无所谓。
* OneDrive 偶尔会在 ffmpeg 写文件时锁住文件，表现是 `PermissionError`。遇到就重跑一次；老是遇到就把仓库挪到 OneDrive 之外。

---

## 2. 配置

```bat
cd /d "E:\OneDrive\Agentic AI\daily-podcast-kit"
copy config.env.example config.env
```

`config.env` 是唯一的配置文件，每个子命令自己读它，不需要事先 `source`。已存在的环境变量优先于文件里的值。

---

## 3. HuggingFace

拿 token、Space 命名、第一次发布、手机检查、公开或私有、常见报错，都在 `docs/QUICKSTART.zh-CN.md` §3；
页面本身的机制见 `docs/WEB_PAGE.md`。这里不再重复。

---

## 4. 先手动跑一遍

先跑一次 `prepare` 出提案（题目取 `prompts\queue.md` 第一行），确认后写稿，再本地预览，
确认每一步在这台机器上都能过：

```bat
cd /d "E:\OneDrive\Agentic AI\daily-podcast-kit"
.venv\Scripts\python.exe scripts\podcast.py prepare
rem 打开 episodes\001\topic.md，在 CHOICE: 后面写下选择
.venv\Scripts\python.exe scripts\podcast.py prepare --write
.venv\Scripts\python.exe scripts\build_site.py site
.venv\Scripts\python.exe scripts\podcast.py align site\index.html
.venv\Scripts\python.exe -m http.server 8123 --directory site
```

然后浏览器打开 <http://localhost:8123>。不要直接双击 `site\index.html`：超过 700 KB 的音频是靠页面上的
「Load audio」按钮 fetch 下来的，`file://` 下浏览器不允许这样做，按钮会没反应。
在 Claude 里说「预览站点」也行，`.claude\launch.json` 里配了同样的服务器。

合成那一步会打印实际时长和按字数估算的时长，两者应该接近。差很多就是 `LESSONS.md` §3。
本地页面正常后再 `publish`。每个子命令都把输出追加到 `logs\<子命令>_<日期>.log`。

---

## 5. 定时：prepare 用任务计划程序，publish 用 routine

两个任务的需求不一样，所以分开挂：

* `prepare` 不需要会话，只需要**准点**。Claude 桌面版的 routine 只在应用开着时触发，关着就拖到下次打开才补跑，
  提案会错过你早上看它的时间；系统计划任务能唤醒电脑、错过后开机即补。
  它只出提案、不写稿，所以无人值守也不会产出没人看过的节目；`prepare --write` 不挂定时，由你确认后手动跑。
* `publish` 需要一个 Claude 会话：发布后用浏览器以手机视口验证播放，再把结果汇报给你。

### 5.1 prepare：Windows 任务计划程序

在 **PowerShell** 里建一次：

```powershell
$py  = "E:\OneDrive\Agentic AI\daily-podcast-kit\.venv\Scripts\python.exe"
$act = New-ScheduledTaskAction -Execute $py -Argument '"E:\OneDrive\Agentic AI\daily-podcast-kit\scripts\podcast.py" prepare' -WorkingDirectory "E:\OneDrive\Agentic AI\daily-podcast-kit"
$trg = New-ScheduledTaskTrigger -Daily -At 22:00
$set = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskPath "\Podcast\" -TaskName "Prepare" -Action $act -Trigger $trg -Settings $set
```

* 以当前用户、登录状态下运行，`claude` 命令行用的是你自己的登录。电脑可以睡眠，不能注销。
* 输出在 `logs\prepare_日期.log`。手动触发：`Start-ScheduledTask -TaskPath "\Podcast\" -TaskName "Prepare"`。
* 不要再建一个 `podcast-prepare` routine：两边同时跑会撞在同一个 `episodes/NNN/` 上。

### 5.2 publish：Claude 桌面版 routine

routine 就是一个定时启动的新会话，带一段固定 prompt，所以 prompt 要自包含，路径写绝对路径。

**Routine 2 · 早上 09:00 · `podcast-publish`**

```
仓库：E:\OneDrive\Agentic AI\daily-podcast-kit
1. 用 Bash 工具在该目录下运行：
     .venv/Scripts/python.exe scripts/podcast.py publish
   如果它报 "prepare ran less than an hour ago"，说明昨晚的任务被推迟到刚才才跑，稿子还没人看过。
   这种情况直接停下来告诉我，不要加 --now。
2. 输出里有 SERVE_URL= 的话，用浏览器工具以手机视口打开这个地址，点最新一集的播放按钮，
   等 5 秒，确认播放时间在前进、字幕在跟着高亮。
3. 汇报三件事：发布了哪几集（"New episode ready" 那些行）、SERVE_URL、手机端播放验证结果。
   失败就贴错误原文。最多重试一次，不要改任何文件。
```

* **先点一次 Run now**，看着它跑。第一次 Bash 命令会弹权限确认，选「总是允许」。
* 桌面版关着时 routine 会拖到下次打开才跑；晚一点发布没有害处。
* `publish` 发现 `prepare` 一小时内刚跑过就拒绝发布，等你看完稿子再手动 `publish --now`。
* 完成通知会回到创建 routine 的那个会话。

---

## 6. 不用 Claude 桌面版

`publish` 也可以挂成计划任务：把 5.1 里的 `prepare` 换成 `publish`、`Prepare` 换成 `Publish`、时间换成 09:00。
代价是没有浏览器验证那一步，发布后自己在手机上看一眼。

---

## 7. 每天怎么用

1. 晚上 22:00 后看一眼 `logs\prepare_日期.log`，最后应有 `=== PROPOSED: episode NNN`。
2. 读 `episodes\NNN\topic.md`，把选中的候选号写在 `CHOICE:` 后面；提案说拿不到的原文，
   你能找到就放进 `materials\NNN\`。整批都不想要就删掉这个目录。
3. 跑 `.venv\Scripts\python.exe scripts\podcast.py prepare --write`，等 `=== READY: episode NNN`。
4. 发布前审稿：`episodes\NNN\script.txt`。
   * 改了正文 → 删掉 `episodes\NNN\audio\` 目录，早上会重新合成。
   * 不想要这集 → 删掉整个 `episodes\NNN\` 目录。早上会重新发布已有的页面，日志里写「No new episode today」。
5. 09:00 发布，手机上听。

周报不在这两个定时任务里，是按需跑的第三个命令：`python scripts\podcast.py weekly --topic "..."`。
它只安装 issue 并重建本地页面，审完之后由下一次 `publish` 带上去。字段和编辑流程见 `docs/WEEKLY.md`。

---

## 8. Windows 专属排错

| 现象 | 看哪里 |
|---|---|
| `Python was not found; run without arguments to install` | 你敲的是 `python3`，Windows 上没有；用 `python` 或虚拟环境的完整路径 |
| `WinError 1114 ... c10.dll` | torch 版本太新，按 1.1 固定到 2.5.1 |
| `'claude' is not recognized` | 计划任务或 routine 的 PATH 里没有 `C:\Users\<你>\.local\bin`；`where claude` 确认位置 |
| `PermissionError` 出现在 `audio\` 目录 | OneDrive 正在同步那个文件；重跑，或把仓库挪出 OneDrive |
| 控制台里中文或表情变乱码 | 脚本已强制 UTF-8；如果是你自己另写的脚本，设 `PYTHONUTF8=1` |
| routine 到点没跑 | 桌面版没开，打开后会补跑；所以 `prepare` 挂的是系统计划任务，见 §5 |
| `publish` 报 `prepare ran less than an hour ago` | 这是保护，不是故障；审完稿子再 `publish --now` |
