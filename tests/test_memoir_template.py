"""Tests for the memoir template (Item 15)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import build_tex, main


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "book"
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


def test_memoir_template_uses_memoir_class(tmp_path, monkeypatch):
    """memoir template emits \\documentclass{memoir}."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Thesis\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "memoir", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\documentclass" in out
    assert "{memoir}" in out
    assert "{book}" not in out


def test_memoir_default_chapter_style(tmp_path, monkeypatch):
    """Absent chapter-style YAML key -> the template's default \\chapterstyle."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Thesis\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "memoir", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\chapterstyle{ default }" in out


def test_memoir_chapter_style_override(tmp_path, monkeypatch):
    """`chapter-style: veelo` emits \\chapterstyle{veelo}."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\nchapter-style: veelo\n---\n\n# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "memoir", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\chapterstyle{ veelo }" in out
    assert "\\chapterstyle{ default }" not in out


def test_memoir_natbib_loaded_once(tmp_path, monkeypatch):
    """memoir composes with natbib without a double-load conflict."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Thesis\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "memoir", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert out.count("\\usepackage{natbib}") == 1


def test_memoir_emits_include_for_top_level_embeds(tmp_path, monkeypatch):
    """memoir is book-family: top-level embeds produce \\include{stem}."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "root.md").write_text(
        "---\ntitle: A Thesis\njournal:\n  template: memoir\n---\n\n![](chapter1.md)\n"
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
    assert "{memoir}" in root_tex


def test_book_fixture_with_memoir_template(tmp_path, monkeypatch):
    """Book fixture with template swapped to memoir builds cleanly."""
    src = tmp_path / "src"
    src.mkdir()
    for name in ("chapter1.md", "chapter2.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())
    root_text = FIXTURE_DIR.joinpath("root.md").read_text().replace(
        "template: book", "template: memoir"
    )
    (src / "root.md").write_text(root_text)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = (build_dir / "root.tex").read_text()
    assert "{memoir}" in root_tex
    assert "\\include{chapter1}" in root_tex
    assert "\\include{chapter2}" in root_tex
    assert (build_dir / "chapter1.tex").exists()
    assert (build_dir / "chapter2.tex").exists()
