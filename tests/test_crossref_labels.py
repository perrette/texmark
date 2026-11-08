"""Tests for the texmark-crossref-labels filter: references to labelled
figures, tables, sections, listings and equations within one document."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import panflute as pf
import pytest

from texmark.build import build_tex, main
from texmark.filters.crossref_labels import CrossrefLabelsFilter
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent
pytestmark_pandoc = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")


# --- Unit tests: build the AST pandoc would hand us, no pandoc needed. ---

def _cite(*keys):
    return pf.Cite(pf.Str("@" + keys[0]), citations=[pf.Citation(k) for k in keys])


def _run(*inlines, metadata=None, journal_prefixes=None):
    f = CrossrefLabelsFilter(journal_prefixes)
    doc = pf.Doc(pf.Para(*inlines), metadata=metadata or {})
    f.prepare(doc)
    return list(doc.walk(f.action).content[0].content)


def _text(*keys, **kw):
    inlines = _run(_cite(*keys), **kw)
    assert len(inlines) == 1 and isinstance(inlines[0], pf.RawInline)
    return inlines[0].text


WORDS = {"crossref": {
    "fig": "Fig.", "figs": "Figs.", "eq": "Eq.", "eqs": "Eqs.",
    "tbl": "Table", "tbls": "Tables", "sec": "Sect.", "secs": "Sects.",
    "lst": "Listing", "lsts": "Listings",
}}


@pytest.mark.parametrize("key, bare, worded", [
    ("fig:x", "\\ref{fig:x}", "Fig.~\\ref{fig:x}"),
    ("eq:x", "\\eqref{eq:x}", "Eq.~\\eqref{eq:x}"),
    ("tbl:x", "\\ref{tbl:x}", "Table~\\ref{tbl:x}"),
    ("sec:x", "\\ref{sec:x}", "Sect.~\\ref{sec:x}"),
    ("lst:x", "\\ref{lst:x}", "Listing~\\ref{lst:x}"),
])
def test_single_reference(key, bare, worded):
    assert _text(key) == bare  # default: the bare number, as before
    assert _text(key, metadata=WORDS) == worded


def test_two_references_in_one_bracket():
    assert _text("fig:a", "fig:b") == "\\ref{fig:a} and~\\ref{fig:b}"
    assert _text("fig:a", "fig:b", metadata=WORDS) == "Figs.~\\ref{fig:a} and~\\ref{fig:b}"


def test_three_references_in_one_bracket():
    assert _text("fig:a", "fig:b", "fig:c") == "\\ref{fig:a}, \\ref{fig:b} and~\\ref{fig:c}"
    assert _text("fig:a", "fig:b", "fig:c", metadata=WORDS) == (
        "Figs.~\\ref{fig:a}, \\ref{fig:b} and~\\ref{fig:c}")


def test_plural_equations():
    assert _text("eq:a", "eq:b") == "\\eqref{eq:a} and~\\eqref{eq:b}"
    assert _text("eq:a", "eq:b", metadata=WORDS) == "Eqs.~\\eqref{eq:a} and~\\eqref{eq:b}"


def test_mixed_kinds():
    assert _text("fig:a", "fig:b", "tbl:t") == "\\ref{fig:a} and~\\ref{fig:b} and \\ref{tbl:t}"
    assert _text("fig:a", "fig:b", "tbl:t", metadata=WORDS) == (
        "Figs.~\\ref{fig:a} and~\\ref{fig:b} and Table~\\ref{tbl:t}")


@pytest.mark.parametrize("keys", [("smith2020",), ("fig:a", "smith2020"), ("my-heading",),
                                  ("tab:x",), ("fig:",)])
def test_real_citations_left_alone(keys):
    assert isinstance(_run(_cite(*keys))[0], pf.Cite)


def test_prose_inside_the_bracket_is_kept():
    c = pf.Cite(pf.Str("[see @fig:a, left]"),
                citations=[pf.Citation("fig:a", prefix=[pf.Str("see")], suffix=[pf.Str("left")])])
    out = _run(c)[0]
    assert isinstance(out, pf.Span)
    assert [type(e).__name__ for e in out.content] == ["Str", "RawInline", "Str"]
    assert out.content[1].text == "\\ref{fig:a}"


def test_frontmatter_sets_some_prefixes_only():
    meta = {"crossref": {"fig": "Figure", "figs": "Figures", "eq": "Equation"}}
    assert _text("fig:a", "fig:b", metadata=meta) == "Figures~\\ref{fig:a} and~\\ref{fig:b}"
    assert _text("eq:a", metadata=meta) == "Equation~\\eqref{eq:a}"
    assert _text("tbl:a", metadata=meta) == "\\ref{tbl:a}"  # no word configured


def test_journal_prefixes_sit_between_default_and_frontmatter():
    journal = {"fig": "Figure", "sec": "Section"}
    assert _text("fig:a", journal_prefixes=journal) == "Figure~\\ref{fig:a}"
    assert _text("tbl:a", journal_prefixes=journal) == "\\ref{tbl:a}"
    meta = {"crossref": {"fig": "Fig"}}
    assert _text("fig:a", journal_prefixes=journal, metadata=meta) == "Fig~\\ref{fig:a}"
    meta = {"crossref": {"fig": ""}}  # an explicit empty word switches it off again
    assert _text("fig:a", journal_prefixes=journal, metadata=meta) == "\\ref{fig:a}"


def test_prefixes_do_not_leak_between_documents():
    f = CrossrefLabelsFilter()
    for meta, expected in [({"crossref": {"fig": "Figure"}}, "Figure~\\ref{fig:a}"), ({}, "\\ref{fig:a}")]:
        doc = pf.Doc(pf.Para(_cite("fig:a")), metadata=meta)
        f.prepare(doc)
        assert doc.walk(f.action).content[0].content[0].text == expected


@pytest.mark.parametrize("url, text, expected", [
    ("#eq:foo", [], "\\eqref{eq:foo}"),
    ("#fig:foo", [pf.Str("#")], "\\ref{fig:foo}"),
    ("#tbl:foo", [], "\\ref{tbl:foo}"),
    ("#sec:foo", [], "\\ref{sec:foo}"),
    ("#my-heading", [pf.Str("#")], "\\ref{my-heading}"),
])
def test_hash_links_give_the_bare_number(url, text, expected):
    out = _run(pf.Link(*text, url=url))[0]
    assert isinstance(out, pf.RawInline) and out.text == expected


def test_links_with_words_or_other_targets_left_alone():
    assert isinstance(_run(pf.Link(pf.Str("some"), url="#my-heading"))[0], pf.Link)
    assert isinstance(_run(pf.Link(url="https://example.org"))[0], pf.Link)


# --- Integration: markdown -> .tex (and PDF when TeX is available) ---

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc000000301010018dd8db00000000049454e44ae426082")

DOC = """\
---
title: Labels
journal:
  template: {template}
{extra}---

# Introduction {{#sec:intro}}

Figure: @fig:a and [@fig:a], pair [@fig:a; @fig:b], triple [@fig:a; @fig:b; @tbl:t].
Also @tbl:t, @sec:intro, @eq:e and [@eq:e], and by link [#](#eq:e).

![Caption A](figs/a.png){{#fig:a}}

![Caption B](figs/b.png){{#fig:b}}

| a | b |
|---|---|
| 1 | 2 |

: A table {{#tbl:t}}

$$ x = y $$ {{#eq:e}}

An unlabelled one stays unnumbered:

$$ z = w $$
"""


def _write(tmp_path, template="arxiv", extra=""):
    (tmp_path / "figs").mkdir()
    for name in ("a", "b"):
        (tmp_path / "figs" / f"{name}.png").write_bytes(PNG)
    md = tmp_path / "doc.md"
    md.write_text(DOC.format(template=template, extra=extra))
    return md


@pytestmark_pandoc
def test_build_tex_labels_and_references(tmp_path, monkeypatch):
    md = _write(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"), journal_template="arxiv")
    tex = out.read_text()
    # labels
    assert "\\label{sec:intro}" in tex
    assert "\\label{fig:a}" in tex and "\\label{fig:b}" in tex
    assert "\\label{tbl:t}" in tex
    assert "\\begin{equation}\\label{eq:e} x = y \\end{equation}" in tex
    assert "{#eq:e}" not in tex
    assert "\\[ z = w \\]" in tex
    # references: bare numbers by default, several keys joined (no citations)
    flat = tex.replace("\n", " ")
    assert "Figure: \\ref{fig:a} and \\ref{fig:a}" in flat
    assert "pair \\ref{fig:a} and~\\ref{fig:b}" in flat
    assert "triple \\ref{fig:a} and~\\ref{fig:b} and \\ref{tbl:t}" in flat
    assert "\\ref{tbl:t}, \\ref{sec:intro}, \\eqref{eq:e} and \\eqref{eq:e}" in flat
    assert "by link \\eqref{eq:e}" in flat
    assert "Fig." not in tex and "Table~" not in tex
    assert "\\cite" not in tex and "\\citep" not in tex and "\\citet" not in tex


@pytestmark_pandoc
def test_build_tex_frontmatter_prefixes(tmp_path, monkeypatch):
    md = _write(tmp_path, extra="crossref:\n  fig: Fig.\n  figs: Figs.\n  tbl: Table\n  eq: Eq.\n  sec: Sect.\n")
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"), journal_template="arxiv")
    flat = out.read_text().replace("\n", " ")
    assert "Figure: Fig.~\\ref{fig:a} and Fig.~\\ref{fig:a}" in flat
    assert "pair Figs.~\\ref{fig:a} and~\\ref{fig:b}" in flat
    assert "Figs.~\\ref{fig:a} and~\\ref{fig:b} and Table~\\ref{tbl:t}" in flat
    assert "Table~\\ref{tbl:t}, Sect.~\\ref{sec:intro}, Eq.~\\eqref{eq:e}" in flat
    assert "by link \\eqref{eq:e}" in flat  # links stay bare


def test_journal_chain_uses_journal_prefixes():
    from texmark.journals import journal_chain
    chain = journal_chain({"crossref": {"fig": "Figure"}})
    (labels,) = [f for f in chain if isinstance(f, CrossrefLabelsFilter)]
    doc = pf.Doc(pf.Para(_cite("fig:a")))
    labels.prepare(doc)
    assert doc.walk(labels.action).content[0].content[0].text == "Figure~\\ref{fig:a}"


@pytestmark_pandoc
@pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                    reason="latexmk/pdflatex not available")
def test_pdf_has_no_undefined_references(tmp_path, monkeypatch):
    md = _write(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT))
    build = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-d", str(build), "--pdf"])
    main()
    log = (build / "doc.log").read_text()
    assert "undefined" not in log, [l for l in log.splitlines() if "undefined" in l]
    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(build / "doc.pdf"), "-"],
                              capture_output=True, text=True).stdout
        assert "?" not in text
        assert "pair 1 and 2" in text.replace("\n", " ")
