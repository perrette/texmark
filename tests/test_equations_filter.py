"""Tests for the texmark-equations filter."""
from __future__ import annotations

from pathlib import Path

import panflute as pf
import pytest

from texmark.build import build_tex
from texmark.filters.equations import equations_filter
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent


# --- Unit tests: construct the AST pandoc would hand us, no pandoc needed. ---

def _run(*inlines):
    """Walk a one-paragraph doc through the filter and return the resulting
    paragraph's inline list."""
    doc = pf.Doc(pf.Para(*inlines))
    out = doc.walk(equations_filter)
    return list(out.content[0].content)


def _display(body):
    return pf.Math(body, format="DisplayMath")


def test_plain_display_math_left_alone():
    inlines = _run(_display("x = y"))
    assert isinstance(inlines[0], pf.Math)  # untouched -> pandoc emits \[ \]


def test_class_names_the_environment():
    inlines = _run(_display("x = y"), pf.Str("{.gather}"))
    assert len(inlines) == 1
    assert isinstance(inlines[0], pf.RawInline)
    assert inlines[0].text == "\\begin{gather}x = y\\end{gather}"


def test_bare_label_implies_equation():
    inlines = _run(_display("E = mc^2"), pf.Str("{#eq:emc}"))
    assert inlines[0].text == "\\begin{equation}\\label{eq:emc}E = mc^2\\end{equation}"


def test_equation_keeps_inner_aligned():
    body = "\n\\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}\n"
    inlines = _run(_display(body), pf.Str("{#eq:foo}"), pf.Space(), pf.Str(".equation}"))
    # NB: split trailer "{#eq:foo .equation}" arrives as several inlines.
    text = inlines[0].text
    assert "\\begin{equation}\\label{eq:foo}" in text
    assert "\\begin{aligned}" in text  # preserved -> single number


def test_align_unwraps_inner_aligned():
    body = "\n\\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}\n"
    inlines = _run(_display(body), pf.Str("{.align}"))
    text = inlines[0].text
    assert text.startswith("\\begin{align}")
    assert "aligned" not in text  # unwrapped -> per-row numbers
    assert "a &= b" in text


def test_align_with_label_unwraps_and_labels():
    body = "\\begin{aligned}a &= b \\\\ c &= d\\end{aligned}"
    inlines = _run(_display(body), pf.Str("{#eq:m"), pf.Space(), pf.Str(".align}"))
    text = inlines[0].text
    assert text.startswith("\\begin{align}\\label{eq:m}")
    assert "aligned" not in text


def test_trailer_is_consumed_not_leaked():
    inlines = _run(_display("x = y"), pf.Str("{.equation}"))
    # The Str("{.equation}") must be gone, replaced by nothing extra.
    assert len(inlines) == 1


def test_cite_ref_to_eqref():
    inlines = _run(pf.Cite(pf.Str("@eq:foo"),
                           citations=[pf.Citation("eq:foo")]))
    assert isinstance(inlines[0], pf.RawInline)
    assert inlines[0].text == "\\eqref{eq:foo}"


def test_non_eq_cite_left_alone():
    inlines = _run(pf.Cite(pf.Str("@smith2020"),
                           citations=[pf.Citation("smith2020")]))
    assert isinstance(inlines[0], pf.Cite)


def test_link_ref_to_eqref():
    inlines = _run(pf.Link(url="#eq:foo"))
    assert isinstance(inlines[0], pf.RawInline)
    assert inlines[0].text == "\\eqref{eq:foo}"


def test_non_eq_link_left_alone():
    inlines = _run(pf.Link(pf.Str("x"), url="#section"))
    assert isinstance(inlines[0], pf.Link)


def test_unknown_env_passes_through_with_warning(caplog):
    inlines = _run(_display("x = y"), pf.Str("{.equaton}"))
    assert inlines[0].text == "\\begin{equaton}x = y\\end{equaton}"
    assert any("unknown math environment" in r.message for r in caplog.records)


# --- Integration: through build_tex / pandoc. ---

pytestmark_pandoc = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


@pytestmark_pandoc
def test_build_tex_equations_end_to_end(tmp_path):
    md = tmp_path / "eq.md"
    md.write_text(
        "---\ntitle: Eq\njournal:\n  template: arxiv\n---\n\n# Math\n\n"
        "$$\n\\begin{aligned}\na &= b \\\\\nc &= d\n\\end{aligned}\n$$ {#eq:p .align}\n\n"
        "$$\n\\begin{aligned}\ne &= f\n\\end{aligned}\n$$ {#eq:q .equation}\n\n"
        "$$ x = y $$\n\n"
        "See [](#eq:p) and @eq:q.\n"
    )
    out = tmp_path / "build" / "eq.tex"
    build_tex(str(md), str(out), build_dir=str(tmp_path / "build"),
              journal_template="arxiv")
    text = out.read_text()
    # per-row align, inner aligned unwrapped
    assert "\\begin{align}\\label{eq:p}" in text
    # single-number equation keeps aligned
    assert "\\begin{equation}\\label{eq:q}" in text
    assert "\\begin{aligned}" in text
    # plain stays unnumbered
    assert "\\[ x = y \\]" in text
    # refs
    assert text.count("\\eqref{eq:p}") == 1
    assert "\\eqref{eq:q}" in text
