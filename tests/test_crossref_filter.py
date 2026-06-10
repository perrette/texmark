"""Tests for the texmark-crossref filter (Item 4)."""
from __future__ import annotations

import os
from pathlib import Path

import panflute as pf
import pytest

from texmark.build import build_tex
from texmark.filters.crossref import CrossrefFilter, crossref_filter
from tests import pandoc_available


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "companions"
REPO_ROOT = Path(__file__).parent.parent


# Unit tests: don't need pandoc.

def _stems_doc(own: str, comp: list[str], emb: list[str] | None = None) -> pf.Doc:
    ctx = {
        "crossref_own_stem": own,
        "crossref_companion_stems": comp,
    }
    if emb is not None:
        ctx["crossref_embed_stems"] = emb
    return pf.Doc(metadata={"texmark": ctx})


def test_link_with_known_stem_rewritten_to_ref():
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=["si"])
    doc.content = [pf.Para(pf.Link(pf.Str("Fig"), url="si.md#fig:noise"))]
    f.prepare(doc)
    out = doc.walk(f.action)
    inline = out.content[0].content[0]
    assert isinstance(inline, pf.RawInline)
    assert inline.text == "\\ref{si:fig:noise}"


def test_link_without_anchor_left_alone():
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=["si"])
    doc.content = [pf.Para(pf.Link(pf.Str("si"), url="si.md"))]
    f.prepare(doc)
    out = doc.walk(f.action)
    assert isinstance(out.content[0].content[0], pf.Link)


def test_pdf_link_left_alone_even_with_anchor():
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=["si"])
    doc.content = [pf.Para(pf.Link(pf.Str("S"), url="smith.pdf#section"))]
    f.prepare(doc)
    out = doc.walk(f.action)
    assert isinstance(out.content[0].content[0], pf.Link)


def test_link_to_unknown_stem_left_alone():
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=["si"])
    doc.content = [pf.Para(pf.Link(pf.Str("X"), url="other.md#fig:x"))]
    f.prepare(doc)
    out = doc.walk(f.action)
    assert isinstance(out.content[0].content[0], pf.Link)


def test_own_stem_self_reference_left_alone():
    """A link to one's own stem (e.g. [foo](main.md#bar) inside main) is
    not a cross-doc ref — keep it untouched so the usual hyperref/\\ref
    machinery handles it."""
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=["si"])
    doc.content = [pf.Para(pf.Link(pf.Str("X"), url="main.md#fig:result"))]
    f.prepare(doc)
    out = doc.walk(f.action)
    assert isinstance(out.content[0].content[0], pf.Link)


def test_finalize_emits_xr_preamble():
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=["si"])
    f.prepare(doc)
    f.finalize(doc)
    text = doc.metadata["xr_preamble"].text
    assert "\\usepackage{xr-hyper}" in text
    assert "\\externaldocument[si:]{si}" in text


def test_finalize_no_targets_no_metadata_write():
    f = CrossrefFilter()
    doc = _stems_doc(own="main", comp=[])
    f.prepare(doc)
    f.finalize(doc)
    assert "xr_preamble" not in doc.metadata.content


# Integration tests: run pandoc through build_tex.

pytestmark_pandoc = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytest.fixture
def _subprocess_finds_local_texmark(monkeypatch):
    """Ensure pandoc-launched filter subprocesses import the in-tree texmark."""
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


@pytestmark_pandoc
def test_build_main_emits_externaldocument_and_ref(
    tmp_path, _subprocess_finds_local_texmark
):
    src = tmp_path / "src"
    src.mkdir()
    for name in ("main.md", "si.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())

    out = tmp_path / "build" / "main.tex"
    build_tex(
        str(src / "main.md"),
        str(out),
        build_dir=str(tmp_path / "build"),
        journal_template="arxiv",
        companion_stems=["si"],
        own_stem="main",
    )
    text = out.read_text()
    # (a) cross-doc link rewritten
    assert "\\ref{si:fig:noise}" in text
    # (b) xr-hyper preamble injected
    assert "\\usepackage{xr-hyper}" in text
    assert "\\externaldocument[si:]{si}" in text
    # (d) plain external link untouched
    assert "https://example.com" in text
    # .pdf link untouched (kept as hyperlink)
    assert "smith.pdf" in text
    # .md link without #anchor is NOT rewritten to \ref (no anchor, no ref)
    assert "\\ref{other:" not in text


@pytestmark_pandoc
def test_build_si_sees_main_externaldocument_and_ref(
    tmp_path, _subprocess_finds_local_texmark
):
    src = tmp_path / "src"
    src.mkdir()
    for name in ("main.md", "si.md"):
        (src / name).write_text(FIXTURE_DIR.joinpath(name).read_text())

    out = tmp_path / "build" / "si.tex"
    build_tex(
        str(src / "si.md"),
        str(out),
        build_dir=str(tmp_path / "build"),
        journal_template="arxiv",
        companion_stems=["main"],
        own_stem="si",
    )
    text = out.read_text()
    assert "\\ref{main:fig:result}" in text
    assert "\\usepackage{xr-hyper}" in text
    assert "\\externaldocument[main:]{main}" in text


@pytestmark_pandoc
def test_no_companions_means_no_xr_preamble(
    tmp_path, _subprocess_finds_local_texmark
):
    """Single-file build with no companions emits no xr-hyper preamble."""
    md = tmp_path / "solo.md"
    md.write_text(
        "---\ntitle: Solo\njournal:\n  template: arxiv\n---\n\n"
        "# Hello\n\nBody.\n"
    )
    out = tmp_path / "build" / "solo.tex"
    build_tex(
        str(md),
        str(out),
        build_dir=str(tmp_path / "build"),
        journal_template="arxiv",
    )
    text = out.read_text()
    assert "xr-hyper" not in text
    assert "externaldocument" not in text


def test_import_smoke():
    from texmark.filters.crossref import crossref_filter as cf

    assert hasattr(cf, "action")
    assert hasattr(cf, "prepare")
    assert hasattr(cf, "finalize")
