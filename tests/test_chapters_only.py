"""Tests for the `chapters:` YAML key + `--only` flag (Item 13)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import main
from texmark.project import resolve_project


REPO_ROOT = Path(__file__).parent.parent


pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc binary not available on PATH",
)


@pytest.fixture(autouse=True)
def _subprocess_finds_local_texmark(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


# --------------------------------------------------------------------------
# project.py: chapters: union-and-dedup logic
# --------------------------------------------------------------------------

def test_chapters_union_order(tmp_path):
    """Body-discovered embeds come first, then chapters: entries in YAML order."""
    _write(tmp_path / "intro.md", "# Intro\n\nbody\n")
    _write(tmp_path / "ch1.md", "# Ch1\n\nbody\n")
    root = _write(
        tmp_path / "root.md",
        "---\nchapters: [ch1.md]\n---\n\n![](intro.md)\n",
    )
    project = resolve_project([root])
    assert [p.stem for p in project.embedded_files] == ["intro", "ch1"]


def test_chapters_dedup_against_body(tmp_path):
    """A chapter already discovered in the body is not duplicated."""
    _write(tmp_path / "intro.md", "# Intro\n\nbody\n")
    _write(tmp_path / "ch1.md", "# Ch1\n\nbody\n")
    root = _write(
        tmp_path / "root.md",
        "---\nchapters: [intro.md, ch1.md]\n---\n\n![](intro.md)\n",
    )
    project = resolve_project([root])
    # intro stays at its body position; ch1 appended; no duplicate intro.
    assert [p.stem for p in project.embedded_files] == ["intro", "ch1"]


def test_chapters_only_yaml(tmp_path):
    """chapters: with no body embeds still populates embedded_files."""
    _write(tmp_path / "ch1.md", "# Ch1\n\nbody\n")
    _write(tmp_path / "ch2.md", "# Ch2\n\nbody\n")
    root = _write(
        tmp_path / "root.md",
        "---\nchapters: [ch1.md, ch2.md]\n---\n\nNo body embeds.\n",
    )
    project = resolve_project([root])
    assert [p.stem for p in project.embedded_files] == ["ch1", "ch2"]


# --------------------------------------------------------------------------
# build.py + book template: --only -> \includeonly, plus chapters composition
# --------------------------------------------------------------------------

def _book_root(tmp_path: Path, *, body_embed=None, chapters=None):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    _write(src / "intro.md", "---\ntitle: Intro\n---\n\n# Intro\n\nIntro body.\n")
    _write(src / "ch1.md", "---\ntitle: Ch1\n---\n\n# Chapter 1\n\nCh1 body.\n")
    lines = ["---", "title: A Book", "journal:", "  template: book"]
    if chapters:
        lines.append("chapters: [" + ", ".join(chapters) + "]")
    lines.append("---")
    lines.append("")
    if body_embed:
        lines.append(f"![]({body_embed})")
    _write(src / "root.md", "\n".join(lines) + "\n")
    return src


def test_only_emits_includeonly_for_book(tmp_path, monkeypatch):
    """`--only ch1.md` on a book template injects \\includeonly{ch1}."""
    src = _book_root(tmp_path, chapters=["ch1.md"])
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["texmark", str(src / "root.md"), "-d", str(build_dir), "--only", "ch1.md"],
    )
    main()
    root_tex = (build_dir / "root.tex").read_text()
    assert "\\includeonly{ch1}" in root_tex


def test_chapters_and_only_compose(tmp_path, monkeypatch):
    """body ![](intro.md) + chapters:[ch1.md] + --only ch1.md:
    master \\include's both intro and ch1; only ch1 typeset."""
    src = _book_root(tmp_path, body_embed="intro.md", chapters=["ch1.md"])
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["texmark", str(src / "root.md"), "-d", str(build_dir), "--only", "ch1.md"],
    )
    main()
    root_tex = (build_dir / "root.tex").read_text()
    # Both chapters are part of the document...
    assert "\\include{intro}" in root_tex
    assert "\\include{ch1}" in root_tex
    # ...but only ch1 is typeset this pass.
    assert "\\includeonly{ch1}" in root_tex
    # Body-only chunks were written for both.
    assert (build_dir / "intro.tex").exists()
    assert (build_dir / "ch1.tex").exists()


def test_only_ignored_for_article(tmp_path, monkeypatch, caplog):
    """`--only` is a no-op (with warning) for article-class templates."""
    src = tmp_path / "src"
    src.mkdir()
    _write(src / "ch1.md", "---\ntitle: Ch1\n---\n\n# Ch1\n\nbody.\n")
    _write(
        src / "root.md",
        "---\ntitle: Paper\njournal:\n  template: arxiv\nchapters: [ch1.md]\n---\n\nNo body embeds.\n",
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys, "argv",
        ["texmark", str(src / "root.md"), "-d", str(build_dir), "--only", "ch1.md"],
    )
    import logging
    with caplog.at_level(logging.WARNING):
        main()
    root_tex = (build_dir / "root.tex").read_text()
    assert "\\includeonly" not in root_tex
    assert any("--only is meaningful only for book-family" in r.message
               for r in caplog.records)


def test_single_file_unaffected(tmp_path, monkeypatch):
    """A plain single-file book build emits no \\includeonly directive."""
    src = tmp_path / "src"
    src.mkdir()
    md = _write(src / "doc.md", "---\ntitle: T\njournal:\n  template: book\n---\n\n# A\n\nbody.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-d", str(build_dir)])
    main()
    out = (build_dir / "doc.tex").read_text()
    assert "\\includeonly" not in out
