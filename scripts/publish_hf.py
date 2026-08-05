#!/usr/bin/env python3
"""Publish the built site to ONE HuggingFace static Space.

The whole series lives in a single Space: every episode accumulates on one page, so the
URL never changes and the back catalogue is the page. Do NOT create a Space per episode.

Static Spaces are free. Gradio/Docker Spaces require a PRO account and will fail with
HTTP 402, so keep this static — the site needs no server anyway.

Usage: publish_hf.py [site_dir]
Env:   HF_TOKEN         write token from huggingface.co/settings/tokens
       PODCAST_SPACE    e.g. your-username/daily-podcast
       PODCAST_TITLE    optional, shown on the Space card
"""
import os
import sys

from huggingface_hub import HfApi, create_repo

TOKEN = os.environ["HF_TOKEN"]
REPO = os.environ["PODCAST_SPACE"]
TITLE = os.environ.get("PODCAST_TITLE", "Daily Podcast")
api = HfApi(token=TOKEN)

README = f"""---
title: {TITLE}
emoji: 🎙
colorFrom: indigo
colorTo: blue
sdk: static
pinned: false
---

A daily ten-minute podcast. Every episode has a synced transcript, comprehension
questions and links to its sources.
Use the **Community** tab to request a topic — feedback shapes what gets made next.
"""


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    site = sys.argv[1] if len(sys.argv) > 1 else os.path.join(root, "site")

    create_repo(REPO, repo_type="space", space_sdk="static", token=TOKEN, exist_ok=True)
    api.upload_file(path_or_fileobj=README.encode("utf-8"), path_in_repo="README.md",
                    repo_id=REPO, repo_type="space", token=TOKEN)

    # The whole site tree: index.html plus every episode's audio.
    api.upload_folder(folder_path=site, repo_id=REPO, repo_type="space", token=TOKEN,
                      commit_message="Publish site")

    owner, name = REPO.split("/")
    print(f"SITE_URL=https://huggingface.co/spaces/{REPO}")
    print(f"SERVE_URL=https://{owner}-{name}.static.hf.space")
    print(f"DISCUSS_URL=https://huggingface.co/spaces/{REPO}/discussions")


if __name__ == "__main__":
    main()
