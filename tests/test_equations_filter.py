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
    """Run a one-paragraph doc through the filter (prepare + action, as the real
    pipeline does) and return the resulting paragraph's inline list."""
    doc = pf.Doc(pf.Para(*inlines))
    equations_filter.prepare(doc)
    out = doc.walk(equations_filter.action)
    return list(out.content[0].content)


def _run_blocks(*blocks):
    """Run a multi-block doc through the filter and return the resulting blocks."""
    doc = pf.Doc(*blocks)
    equations_filter.prepare(doc)
    out = doc.walk(equations_filter.action)
    return list(out.content)


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


def test_figure_cite_to_plain_ref():
    inlines = _run(pf.Cite(pf.Str("@fig:demo"),
                           citations=[pf.Citation("fig:demo")]))
    assert inlines[0].text == "\\ref{fig:demo}"


def test_table_link_to_plain_ref():
    inlines = _run(pf.Link(url="#tbl:demo"))
    assert inlines[0].text == "\\ref{tbl:demo}"


def test_section_link_to_plain_ref():
    inlines = _run(pf.Link(url="#sec:intro"))
    assert inlines[0].text == "\\ref{sec:intro}"


def test_equation_still_uses_eqref():
    cite = _run(pf.Cite(pf.Str("@eq:foo"), citations=[pf.Citation("eq:foo")]))
    link = _run(pf.Link(url="#eq:foo"))
    assert cite[0].text == "\\eqref{eq:foo}"
    assert link[0].text == "\\eqref{eq:foo}"


def test_unknown_prefix_left_alone():
    # no colon (real citation key) and unknown prefix both fall through
    assert isinstance(_run(pf.Cite(pf.Str("@smith2020"),
                                   citations=[pf.Citation("smith2020")]))[0], pf.Cite)
    assert isinstance(_run(pf.Link(pf.Str("x"), url="#lst:code"))[0], pf.Link)


def test_unknown_env_passes_through_with_warning(caplog):
    inlines = _run(_display("x = y"), pf.Str("{.equaton}"))
    assert inlines[0].text == "\\begin{equaton}x = y\\end{equaton}"
    assert any("unknown math environment" in r.message for r in caplog.records)


# --- Trailer in the following paragraph (blank-line / GitHub-friendly form). ---

def test_trailer_following_paragraph_label_implies_equation():
    blocks = _run_blocks(
        pf.Para(_display("E = mc^2")),
        pf.Para(pf.Str("{#eq:emc}")),
    )
    assert len(blocks) == 1  # the two paragraphs merged into one
    assert blocks[0].content[0].text == \
        "\\begin{equation}\\label{eq:emc}E = mc^2\\end{equation}"


def test_trailer_following_paragraph_align_unwraps():
    body = "\\begin{aligned}a &= b \\\\ c &= d\\end{aligned}"
    blocks = _run_blocks(
        pf.Para(_display(body)),
        pf.Para(pf.Str("{#eq:p"), pf.Space(), pf.Str(".align}")),
    )
    assert len(blocks) == 1
    text = blocks[0].content[0].text
    assert text.startswith("\\begin{align}\\label{eq:p}")
    assert "aligned" not in text


def test_attr_paragraph_without_preceding_math_left_alone():
    blocks = _run_blocks(
        pf.Para(pf.Str("Just prose.")),
        pf.Para(pf.Str("{#eq:foo}")),
    )
    assert len(blocks) == 2  # nothing to attach to -> not merged


def test_trailer_glued_to_following_prose_flows_into_one_paragraph():
    # blank line before the trailer, but prose follows it on the next line with
    # no blank line (the real-world authoring pattern). The equation and the
    # following prose stay in ONE paragraph -- no spurious break.
    blocks = _run_blocks(
        pf.Para(_display("a = b")),
        pf.Para(pf.Str("{#eq:foo}"), pf.SoftBreak,
                pf.Str("where"), pf.Space(), pf.Str("b>0.")),
    )
    assert len(blocks) == 1
    para = pf.stringify(blocks[0])
    assert blocks[0].content[0].text == \
        "\\begin{equation}\\label{eq:foo}a = b\\end{equation}"
    assert "{#eq:foo}" not in para and "where" in para


def test_chained_equations_flow_into_one_paragraph():
    # paragraph ends in one equation and begins with the next equation's trailer:
    # the whole run collapses into a single flowing paragraph.
    blocks = _run_blocks(
        pf.Para(_display("a = b")),
        pf.Para(pf.Str("{#eq:one}"), pf.SoftBreak,
                pf.Str("then"), pf.Space(), _display("c = d")),
        pf.Para(pf.Str("{#eq:two}")),
    )
    assert len(blocks) == 1
    texts = [getattr(x, "text", "") for x in blocks[0].content]
    assert "\\begin{equation}\\label{eq:one}a = b\\end{equation}" in texts
    assert "\\begin{equation}\\label{eq:two}c = d\\end{equation}" in texts


def test_equation_folds_into_preceding_paragraph():
    # An equation introduced by a sentence flows into that sentence's paragraph;
    # no paragraph starts with an equation.
    blocks = _run_blocks(
        pf.Para(pf.Str("We"), pf.Space(), pf.Str("define,")),
        pf.Para(_display("a = b")),
        pf.Para(pf.Str("{#eq:foo}"), pf.SoftBreak, pf.Str("where"), pf.Space(),
                pf.Str("b>0.")),
    )
    assert len(blocks) == 1
    text = pf.stringify(blocks[0])
    assert "define," in text and "where" in text
    assert any(getattr(x, "text", "") ==
               "\\begin{equation}\\label{eq:foo}a = b\\end{equation}"
               for x in blocks[0].content)


def test_equation_after_heading_stays_own_paragraph():
    # Nothing prose to merge into -> the equation paragraph is left alone.
    blocks = _run_blocks(
        pf.Header(pf.Str("Title"), level=2),
        pf.Para(_display("a = b"), pf.Space(), pf.Str("{.equation}")),
    )
    assert len(blocks) == 2
    assert isinstance(blocks[0], pf.Header)


def test_blank_line_after_trailer_keeps_separate_paragraph():
    # a trailer with nothing after it (blank line, then prose) does NOT pull the
    # following prose in -> the author's paragraph break is preserved.
    blocks = _run_blocks(
        pf.Para(_display("a = b")),
        pf.Para(pf.Str("{#eq:foo}")),
        pf.Para(pf.Str("A new paragraph.")),
    )
    assert len(blocks) == 2
    assert blocks[0].content[0].text == \
        "\\begin{equation}\\label{eq:foo}a = b\\end{equation}"
    assert pf.stringify(blocks[1]).strip() == "A new paragraph."


def test_trailer_merge_inside_footnote():
    note = pf.Note(
        pf.Para(_display("x = y")),
        pf.Para(pf.Str("{.equation}")),
    )
    blocks = _run_blocks(pf.Para(pf.Str("text"), note))
    fn = blocks[0].content[1]
    assert isinstance(fn, pf.Note)
    assert len(fn.content) == 1
    assert fn.content[0].content[0].text == "\\begin{equation}x = y\\end{equation}"


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
        # blank-line / GitHub-friendly form: trailer in the next paragraph
        "$$\n\\begin{aligned}\ng &= h\n\\end{aligned}\n$$\n\n{#eq:r}\n\n"
        "$$ x = y $$\n\n"
        "See [](#eq:p), @eq:q and [](#eq:r).\n"
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
    # blank-line trailer attaches from the following paragraph
    assert "\\begin{equation}\\label{eq:r}" in text
    assert "{#eq:r}" not in text  # trailer consumed, not leaked
    # plain stays unnumbered
    assert "\\[ x = y \\]" in text
    # refs
    assert text.count("\\eqref{eq:p}") == 1
    assert "\\eqref{eq:q}" in text
    assert "\\eqref{eq:r}" in text
