"""Tests for the classicthesis template (Item 16)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import build_tex, main


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "book"
REPO_ROOT = Path(__file__).parent.parent
TEMPLATE_DIR = REPO_ROOT / "texmark" / "templates" / "classicthesis"


pytestmark = pytest.mark.skipif(
    shutil.which("pandoc") is None,
    reason="pandoc binary not available on PATH",
)


@pytest.fixture(autouse=True)
def _subprocess_finds_local_texmark(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


def test_classicthesis_sty_and_notice_bundled():
    """The GPL classicthesis.sty and its NOTICE are bundled under the template dir."""
    assert (TEMPLATE_DIR / "classicthesis.sty").is_file()
    assert (TEMPLATE_DIR / "NOTICE").is_file()
    # Sanity: the bundled file is actually the classicthesis package.
    head = (TEMPLATE_DIR / "classicthesis.sty").read_text()[:200]
    assert "classicthesis" in head


def test_classicthesis_uses_scrreprt_class(tmp_path, monkeypatch):
    """classicthesis template emits \\documentclass{scrreprt} and loads classicthesis."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Thesis\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "classicthesis", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\documentclass" in out
    assert "{scrreprt}" in out
    assert "{classicthesis}" in out


def test_classicthesis_default_no_options(tmp_path, monkeypatch):
    """Absent classicthesis-options -> bare \\usepackage{classicthesis}."""
    md = tmp_path / "doc.md"
    md.write_text("---\ntitle: My Thesis\n---\n\n# Introduction\n\nHello.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "classicthesis", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\usepackage{classicthesis}" in out


def test_classicthesis_options_override(tmp_path, monkeypatch):
    """`classicthesis-options: drophead,parts` propagates into the package load."""
    md = tmp_path / "doc.md"
    md.write_text(
        "---\ntitle: My Thesis\nclassicthesis-options: drophead,parts\n---\n\n# Introduction\n\nHello.\n"
    )
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "classicthesis", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "doc.tex").read_text()
    assert "\\usepackage[drophead,parts]{classicthesis}" in out


def test_classicthesis_emits_include_for_top_level_embeds(tmp_path, monkeypatch):
    """classicthesis is book-family: top-level embeds produce \\include{stem}."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "root.md").write_text(
        "---\ntitle: A Thesis\njournal:\n  template: classicthesis\n---\n\n![](chapter1.md)\n"
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
    assert "{scrreprt}" in root_tex


def test_book_fixture_with_classicthesis_template(tmp_path, monkeypatch):
    """Book fixture with template swapped to classicthesis builds cleanly."""
    src = tmp_path / "src"
    src.mkdir()
    for name in ("chapter1.md", "chapter2.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())
    root_text = FIXTURE_DIR.joinpath("root.md").read_text().replace(
        "template: book", "template: classicthesis"
    )
    (src / "root.md").write_text(root_text)
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = (build_dir / "root.tex").read_text()
    assert "{scrreprt}" in root_tex
    assert "{classicthesis}" in root_tex
    assert "\\include{chapter1}" in root_tex
    assert "\\include{chapter2}" in root_tex
    assert (build_dir / "chapter1.tex").exists()
    assert (build_dir / "chapter2.tex").exists()
