"""Each markdown file is read by pandoc once per build (texmark.project.parse_markdown)."""
from __future__ import annotations

from collections import Counter

import pypandoc
import pytest

from texmark.build import _build_parser, build_project, plan_project
from texmark.project import parse_markdown
from tests import pandoc_available


pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


def test_each_file_parsed_once_and_only_edited_file_reparsed(tmp_path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    files = {
        "main.md": "---\ntitle: Main\njournal: book\nchapters: [ch2.md]\n"
                   "companions: [si.md]\n---\n\n# Intro\n\n![](ch1.md)\n",
        "ch1.md": "# One\n\nFirst chapter.\n",
        "ch2.md": "# Two\n\nSecond chapter.\n",
        "si.md": "---\ntitle: SI\n---\n\n# Supplement\n\nText.\n",
    }
    for name, text in files.items():
        (src / name).write_text(text)

    parsed = Counter()
    convert_text = pypandoc.convert_text

    def counting(source, to, format=None, **kwargs):
        if format and format.startswith("markdown"):
            parsed[source] += 1
        return convert_text(source, to, format=format, **kwargs)

    monkeypatch.setattr(pypandoc, "convert_text", counting)
    parse_markdown.cache_clear()

    build = tmp_path / "build"
    args = _build_parser().parse_args(
        [str(src / "main.md"), "-d", str(build), "--tex", str(build / "main.tex")])
    plan = plan_project(args)
    build_project(plan)

    for name, text in files.items():
        assert parsed[text] == 1, name
    assert (build / "main.tex").exists() and (build / "si.tex").exists()

    # --watch rebuild after editing one chapter: only that chapter is parsed.
    parsed.clear()
    edited = files["ch1.md"].replace("First", "Edited first")
    (src / "ch1.md").write_text(edited)
    build_project(plan)

    assert parsed == Counter({edited: 1})
    assert "Edited first" in (build / "ch1.tex").read_text()
