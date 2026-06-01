"""Tests for the report template (Item 14)."""
import os
import sys
from pathlib import Path

import pytest

from texmark.build import build_tex, main
from tests import pandoc_available


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "book"
REPO_ROOT = Path(__file__).parent.parent


pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytest.fixture(autouse=True)
def _subprocess_finds_local_texmark(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def test_report_template_uses_report_class(tmp_path, monkeypatch):
    """report template emits \\documentclass{report} not book."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Report\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "report", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\documentclass" in out
    assert "{report}" in out
    assert "{book}" not in out


def test_report_template_no_frontmatter_commands(tmp_path, monkeypatch):
    """report template must not contain \\frontmatter / \\mainmatter / \\backmatter."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Report\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "report", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\frontmatter" not in out
    assert "\\mainmatter" not in out
    assert "\\backmatter" not in out


def test_report_template_emits_include_for_top_level_embeds(tmp_path, monkeypatch):
    """report is book-family: top-level embeds produce \\include{stem}."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "root.md").write_text(
        "---\ntitle: A Report\njournal:\n  template: report\n---\n\n![](chapter1.md)\n"
    )
    (src / "chapter1.md").write_text("# Chapter 1\n\nContent.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = (build_dir / "root.tex").read_text()
    assert "\\include{chapter1}" in root_tex
    assert "\\input{chapter1}" not in root_tex
    assert "{report}" in root_tex


def test_book_fixture_with_report_template(tmp_path, monkeypatch):
    """Book fixture with template swapped to report builds cleanly."""
    src = tmp_path / "src"
    src.mkdir()
    for name in ("chapter1.md", "chapter2.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())
    # Replace book template with report in root.md
    root_text = FIXTURE_DIR.joinpath("root.md").read_text().replace(
        "template: book", "template: report"
    )
    (src / "root.md").write_text(root_text)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = (build_dir / "root.tex").read_text()
    assert "{report}" in root_tex
    assert "\\include{chapter1}" in root_tex
    assert "\\include{chapter2}" in root_tex
    assert (build_dir / "chapter1.tex").exists()
    assert (build_dir / "chapter2.tex").exists()
