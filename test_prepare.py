#!/usr/bin/env python3
"""The one check that matters for the confirmation gate: an unconfirmed proposal must read as
unconfirmed. If `field` ever returns something truthy for an empty CHOICE line, `prepare --write`
would narrate a topic nobody picked.

    python test_prepare.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from podcast import field                                  # noqa: E402

PROPOSAL = """# 选题提案 · 第 004 集 · 2026-09-19

CHOICE:{choice}

把选中的候选编号写在上面那行的冒号后面。

## 候选 1 · 风暴前的两小时
- 论点：预报的不确定性不是噪声

SOURCE: library
"""

if __name__ == "__main__":
    d = tempfile.mkdtemp()
    path = os.path.join(d, "topic.md")

    for empty in ("", " ", "\t"):
        open(path, "w", encoding="utf-8").write(PROPOSAL.format(choice=empty))
        assert field(path, "CHOICE") == "", f"empty CHOICE read as confirmed: {empty!r}"

    open(path, "w", encoding="utf-8").write(PROPOSAL.format(choice=" 2"))
    assert field(path, "CHOICE") == "2"
    assert field(path, "SOURCE") == "library"
    assert field(path, "QUEUE") == ""                      # absent line, not an error

    open(path, "w", encoding="utf-8").write(PROPOSAL.format(choice=" 讲讲这件事：为什么预报会错"))
    assert field(path, "CHOICE") == "讲讲这件事：为什么预报会错"   # own wording, colons and all

    print("ok")
