"""Tests for the book template + class-aware embed emission (Item 12)."""
import os
import sys
from pathlib import Path

import panflute as pf
import pytest

from texmark.build import build_tex, main
from texmark.filters.embed import embed_filter
from tests import pandoc_available


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "book"
MULTIFILE_FIXTURE_DIR = Path(__file__).parent / "fixtures" / "multifile"
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


def _run_filter_with_meta(doc):
    return pf.run_filter(embed_filter, doc=doc)


def test_embed_filter_emits_include_for_book_top_level():
    """Top-level embed in a book template -> \\include{stem}."""
    doc = pf.Doc(
        pf.Para(pf.Image(url='chapter1.md')),
        metadata={'journal': {'template': 'book'}, 'texmark': {'embed_depth': 0}},
    )
    doc = _run_filter_with_meta(doc)
    assert isinstance(doc.content[0], pf.RawBlock)
    assert doc.content[0].text == '\\include{chapter1}\n'


def test_embed_filter_nested_uses_input_even_in_book():
    """Nested embeds (embed_depth=1) always emit \\input even in book templates."""
    doc = pf.Doc(
        pf.Para(pf.Image(url='chapter1.md')),
        metadata={'journal': {'template': 'book'}, 'texmark': {'embed_depth': 1}},
    )
    doc = _run_filter_with_meta(doc)
    assert isinstance(doc.content[0], pf.RawBlock)
    assert doc.content[0].text == '\\input{chapter1}\n'


def test_embed_filter_article_class_stays_input():
    """Article-class templates always emit \\input regardless of depth."""
    doc = pf.Doc(
        pf.Para(pf.Image(url='chapter1.md')),
        metadata={'journal': {'template': 'arxiv'}, 'texmark': {'embed_depth': 0}},
    )
    doc = _run_filter_with_meta(doc)
    assert doc.content[0].text == '\\input{chapter1}\n'


def test_embed_filter_no_metadata_defaults_to_input():
    """Backward compat: no journal metadata -> \\input (existing tests still pass)."""
    doc = pf.Doc(pf.Para(pf.Image(url='chapter1.md')))
    doc = _run_filter_with_meta(doc)
    assert doc.content[0].text == '\\input{chapter1}\n'


def test_include_link_emits_include_in_book():
    """[](file.md){.include} form also honors class-aware emission."""
    link = pf.Link(pf.Str('X'), url='chapter1.md', classes=['include'])
    doc = pf.Doc(
        pf.Para(link),
        metadata={'journal': {'template': 'book'}, 'texmark': {'embed_depth': 0}},
    )
    doc = _run_filter_with_meta(doc)
    assert doc.content[0].text == '\\include{chapter1}\n'


def test_book_fixture_builds_master_with_include(tmp_path, monkeypatch):
    """End-to-end: book fixture -> master .tex contains \\include{chapter1}+\\include{chapter2}."""
    src = tmp_path / "src"
    src.mkdir()
    for name in ("root.md", "chapter1.md", "chapter2.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())

    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = (build_dir / "root.tex").read_text()
    assert "\\documentclass" in root_tex
    assert "{book}" in root_tex  # \documentclass[...]{book}
    assert "\\include{chapter1}" in root_tex
    assert "\\include{chapter2}" in root_tex
    # Sanity: must NOT have emitted \input for top-level chapters
    assert "\\input{chapter1}" not in root_tex
    assert "\\input{chapter2}" not in root_tex
    # Body-only chunks were written for both chapters
    assert (build_dir / "chapter1.tex").exists()
    assert (build_dir / "chapter2.tex").exists()


def test_article_multifile_fixture_still_uses_input(tmp_path, monkeypatch):
    """Regression: article-class (arxiv) fixture still emits \\input{...}."""
    src = tmp_path / "src"
    src.mkdir()
    for name in ("root.md", "chapter.md"):
        (src / name).write_text(MULTIFILE_FIXTURE_DIR.joinpath(name).read_text())

    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(src / "root.md"), "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    root_tex = (build_dir / "root.tex").read_text()
    assert "\\input{chapter}" in root_tex
    assert "\\include{chapter}" not in root_tex


def test_book_template_invocation_via_journal_template_flag(tmp_path, monkeypatch):
    """`texmark --journal-template book example.md` produces a book-class master."""
    src = tmp_path / "src"
    src.mkdir()
    # Use a minimal single-file invocation against the book template.
    md = src / "example-book.md"
    md.write_text("---\ntitle: T\n---\n\n# Chapter A\n\nBody A.\n")
    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)

    argv = ["texmark", str(md), "-j", "book", "-d", str(build_dir)]
    monkeypatch.setattr(sys, "argv", argv)
    main()

    out = (build_dir / "example-book.tex").read_text()
    assert "\\documentclass" in out and "{book}" in out
