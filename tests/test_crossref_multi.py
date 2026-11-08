"""Same-document references with several keys in one bracket, and ``@lst:``.

Adapted from the tests in PR #10 by Alex Robinson."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import panflute as pf
import pytest

from texmark.build import build_tex, main
from texmark.filters.equations import equations_filter
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent


def _cite(*keys, prefix=(), suffix=()):
    citations = [pf.Citation(k) for k in keys]
    citations[0].prefix = list(prefix)
    citations[-1].suffix = list(suffix)
    return pf.Cite(pf.Str("@" + keys[0]), citations=citations)


def _run(*inlines):
    doc = pf.Doc(pf.Para(*inlines))
    equations_filter.prepare(doc)
    return list(doc.walk(equations_filter.action).content[0].content)


def _text(*keys):
    inlines = _run(_cite(*keys))
    assert len(inlines) == 1 and isinstance(inlines[0], pf.RawInline)
    return inlines[0].text


@pytest.mark.parametrize("key, expected", [
    ("fig:x", "\\ref{fig:x}"),
    ("eq:x", "\\eqref{eq:x}"),
    ("tbl:x", "\\ref{tbl:x}"),
    ("sec:x", "\\ref{sec:x}"),
    ("lst:x", "\\ref{lst:x}"),
])
def test_single_reference(key, expected):
    assert _text(key) == expected


def test_two_keys():
    assert _text("fig:a", "fig:b") == "\\ref{fig:a} and~\\ref{fig:b}"


def test_three_keys():
    assert _text("fig:a", "fig:b", "fig:c") == "\\ref{fig:a}, \\ref{fig:b} and~\\ref{fig:c}"


def test_equation_keys_use_eqref():
    assert _text("eq:a", "eq:b") == "\\eqref{eq:a} and~\\eqref{eq:b}"


def test_mixed_kinds():
    assert _text("fig:a", "tbl:t") == "\\ref{fig:a} and~\\ref{tbl:t}"
    assert _text("fig:a", "fig:b", "tbl:t") == "\\ref{fig:a}, \\ref{fig:b} and~\\ref{tbl:t}"
    assert _text("sec:s", "eq:e", "lst:l") == "\\ref{sec:s}, \\eqref{eq:e} and~\\ref{lst:l}"


@pytest.mark.parametrize("keys", [("fig:a", "smith2020"), ("smith2020", "eq:a"),
                                  ("fig:a", "tab:x"), ("smith2020",), ("tab:x",)])
def test_real_citation_key_keeps_a_citation(keys):
    out = _run(_cite(*keys))[0]
    assert isinstance(out, pf.Cite)
    assert [c.id for c in out.citations] == list(keys)


def test_prose_in_bracket_kept():
    c = _cite("fig:a", "fig:b", prefix=[pf.Str("see")],
              suffix=[pf.Str(","), pf.Space(), pf.Str("left")])
    out = _run(pf.Str("x"), c)[1:]  # replaced in place by the inlines, no group
    assert [type(e).__name__ for e in out] == ["Str", "Space", "RawInline", "Str", "Space", "Str"]
    assert out[2].text == "\\ref{fig:a} and~\\ref{fig:b}"
    assert out[0].text == "see" and out[-1].text == "left"


# --- Integration: markdown -> .tex, and PDF when TeX is available ---

pytestmark_pandoc = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
    "53de0000000c4944415408d763f8cfc000000301010018dd8db00000000049454e44ae426082")

DOC = """\
---
title: Refs
journal:
  template: arxiv
---

# Introduction {#sec:intro}

Single @fig:a, pair [@fig:a; @fig:b], triple [@fig:a; @fig:b; @tbl:t],
equations [@eq:e; @eq:f], prose [see @fig:a; @fig:b, left].
Also @tbl:t and @sec:intro.

![Caption A](figs/a.png){#fig:a}

![Caption B](figs/b.png){#fig:b}

| a | b |
|---|---|
| 1 | 2 |

: A table {#tbl:t}

$$ x = y $$ {#eq:e}

$$ z = w $$ {#eq:f}
"""


def _write(tmp_path):
    (tmp_path / "figs").mkdir()
    for name in ("a", "b"):
        (tmp_path / "figs" / f"{name}.png").write_bytes(PNG)
    md = tmp_path / "doc.md"
    md.write_text(DOC)
    return md


@pytestmark_pandoc
def test_build_tex_multi_key(tmp_path, monkeypatch):
    md = _write(tmp_path)
    monkeypatch.chdir(tmp_path)
    out = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"), journal_template="arxiv")
    flat = out.read_text().replace("\n", " ")
    assert "Single \\ref{fig:a}," in flat
    assert "pair \\ref{fig:a} and~\\ref{fig:b}," in flat
    assert "triple \\ref{fig:a}, \\ref{fig:b} and~\\ref{tbl:t}," in flat
    assert "equations \\eqref{eq:e} and~\\eqref{eq:f}," in flat
    assert "prose see \\ref{fig:a} and~\\ref{fig:b}, left." in flat
    assert "\\ref{tbl:t} and \\ref{sec:intro}" in flat
    assert "\\cite" not in flat


@pytestmark_pandoc
@pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                    reason="latexmk/pdflatex not available")
def test_build_pdf_multi_key_resolves(tmp_path, monkeypatch):
    md = _write(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    build = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-d", str(build), "--pdf"])
    main()
    log = (build / "doc.log").read_text(errors="replace")
    assert "undefined" not in log, [l for l in log.splitlines() if "undefined" in l]
    if shutil.which("pdftotext"):
        text = subprocess.run(["pdftotext", str(build / "doc.pdf"), "-"],
                              capture_output=True, text=True).stdout
        text = " ".join(text.split())
        assert "?" not in text
        assert "pair 1 and 2" in text
        assert "triple 1, 2 and 1" in text
