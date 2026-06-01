"""Tests for numbering-prefix injection into xr_preamble (Item 5)."""
from __future__ import annotations

import os
from pathlib import Path

import panflute as pf
import pytest

from texmark.filters.crossref import CrossrefFilter
from tests import pandoc_available


REPO_ROOT = Path(__file__).parent.parent


def _prefix_doc(prefix: str | None = None, **counter_overrides) -> pf.Doc:
    """Build a minimal panflute Doc with optional prefix metadata."""
    meta: dict = {
        "crossref_own_stem": pf.MetaString("si"),
        "crossref_companion_stems": pf.MetaList(),
    }
    if prefix is not None:
        meta["prefix"] = pf.MetaString(prefix)
    for key, val in counter_overrides.items():
        # Python kwarg underscores → YAML hyphen convention
        meta[key.replace("_", "-")] = pf.MetaString(val)
    return pf.Doc(metadata=meta)


# ---------------------------------------------------------------------------
# Unit tests (no pandoc)
# ---------------------------------------------------------------------------

def test_prefix_all_four_counters_emitted():
    f = CrossrefFilter()
    doc = _prefix_doc(prefix="S")
    f.prepare(doc)
    f.finalize(doc)
    text = doc.metadata["xr_preamble"].text
    assert "\\renewcommand{\\thefigure}{S\\arabic{figure}}" in text
    assert "\\renewcommand{\\thetable}{S\\arabic{table}}" in text
    assert "\\renewcommand{\\theequation}{S\\arabic{equation}}" in text
    assert "\\renewcommand{\\thesection}{S\\arabic{section}}" in text


def test_equation_override_wins_over_prefix():
    f = CrossrefFilter()
    doc = _prefix_doc(prefix="S", equation_prefix="SE")
    f.prepare(doc)
    f.finalize(doc)
    text = doc.metadata["xr_preamble"].text
    assert "\\renewcommand{\\theequation}{SE\\arabic{equation}}" in text
    # Other three counters fall back to the umbrella prefix
    assert "\\renewcommand{\\thefigure}{S\\arabic{figure}}" in text
    assert "\\renewcommand{\\thetable}{S\\arabic{table}}" in text
    assert "\\renewcommand{\\thesection}{S\\arabic{section}}" in text


def test_no_prefix_no_renewcommand_written():
    f = CrossrefFilter()
    doc = _prefix_doc()
    f.prepare(doc)
    f.finalize(doc)
    assert "xr_preamble" not in doc.metadata.content


def test_override_only_no_umbrella_prefix():
    """A single per-counter override without a top-level prefix."""
    f = CrossrefFilter()
    doc = _prefix_doc(figure_prefix="S")
    f.prepare(doc)
    f.finalize(doc)
    text = doc.metadata["xr_preamble"].text
    assert "\\renewcommand{\\thefigure}{S\\arabic{figure}}" in text
    assert "\\renewcommand{\\thetable}" not in text
    assert "\\renewcommand{\\theequation}" not in text
    assert "\\renewcommand{\\thesection}" not in text


def test_prefix_and_xr_preamble_combined():
    """Companions + prefix → both externaldocument and renewcommand in output."""
    meta = {
        "crossref_own_stem": pf.MetaString("si"),
        "crossref_companion_stems": pf.MetaList(pf.MetaString("main")),
        "prefix": pf.MetaString("S"),
    }
    f = CrossrefFilter()
    doc = pf.Doc(metadata=meta)
    f.prepare(doc)
    f.finalize(doc)
    text = doc.metadata["xr_preamble"].text
    assert "\\usepackage{xr-hyper}" in text
    assert "\\externaldocument[main:]{main}" in text
    assert "\\renewcommand{\\thefigure}{S\\arabic{figure}}" in text


# ---------------------------------------------------------------------------
# Integration tests (require pandoc)
# ---------------------------------------------------------------------------

pytestmark_pandoc = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytest.fixture
def _subprocess_finds_local_texmark(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


@pytestmark_pandoc
def test_build_tex_emits_prefix_renewcommands(tmp_path, _subprocess_finds_local_texmark):
    from texmark.build import build_tex

    md = tmp_path / "si.md"
    md.write_text(
        "---\ntitle: SI\nprefix: S\n---\n\n"
        "Body text.\n"
    )
    out = tmp_path / "build" / "si.tex"
    build_tex(
        str(md),
        str(out),
        build_dir=str(tmp_path / "build"),
        journal_template="arxiv",
        companion_stems=["main"],
        own_stem="si",
    )
    text = out.read_text()
    assert "\\renewcommand{\\thefigure}{S\\arabic{figure}}" in text
    assert "\\renewcommand{\\thetable}{S\\arabic{table}}" in text
    assert "\\renewcommand{\\theequation}{S\\arabic{equation}}" in text
    assert "\\renewcommand{\\thesection}{S\\arabic{section}}" in text


@pytestmark_pandoc
def test_build_tex_equation_override(tmp_path, _subprocess_finds_local_texmark):
    from texmark.build import build_tex

    md = tmp_path / "si.md"
    md.write_text(
        "---\ntitle: SI\nprefix: S\nequation-prefix: SE\n---\n\n"
        "Body text.\n"
    )
    out = tmp_path / "build" / "si.tex"
    build_tex(
        str(md),
        str(out),
        build_dir=str(tmp_path / "build"),
        journal_template="arxiv",
        companion_stems=["main"],
        own_stem="si",
    )
    text = out.read_text()
    assert "\\renewcommand{\\theequation}{SE\\arabic{equation}}" in text
    assert "\\renewcommand{\\thefigure}{S\\arabic{figure}}" in text
