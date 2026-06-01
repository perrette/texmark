"""Integration smoke tests: markdown -> .tex for every bundled journal template.

These exercise the full pipeline (pandoc filters + Jinja2 rendering) without
running pdflatex, so they're cheap to run in CI as long as pandoc is on the
PATH. Each test asserts the resulting .tex contains some template-specific
LaTeX command, proving the right template + filters were applied.
"""
from pathlib import Path
import shutil
import textwrap

import pytest

from texmark.build import build_tex


def _pandoc_available():
    if shutil.which("pandoc") is not None:
        return True
    # pypandoc_binary ships the binary inside the package (not on PATH);
    # pypandoc finds it via get_pandoc_path().
    try:
        import pypandoc
        pypandoc.get_pandoc_path()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _pandoc_available(),
    reason="pandoc binary not available (neither on PATH nor via pypandoc)",
)


SAMPLE_MD = textwrap.dedent(
    """\
    ---
    title: "A short sample paper"
    authors:
      - firstname: Test
        lastname: Author
        affiliation: 1
        email: test@example.com
      - firstname: Second
        lastname: Author
        affiliation: 2
    affiliations:
      - "First Institute"
      - "Second Institute"
    date: "2026-05-26"
    bibliography: references.bib
    journal:
        template: {template}
        short: {short}
    ---

    # Abstract

    A short abstract sentence.

    # Introduction

    Some text with a citation [@knutti2008] and inline @tierney_zhu2020.
    """
)


# (template name, expected fragment that proves the right template was used)
TEMPLATES = [
    ("copernicus", r"\documentclass[cp"),
    ("science", r"\scititle"),
    ("ametsoc", r"\documentclass[twocol]{ametsocV6.1}"),
    ("arxiv", r"\documentclass[11pt]{article}"),
    ("elsarticle", r"{elsarticle}"),
    ("agujournal", r"\documentclass[final]{agujournal2019}"),
    ("springernature", r"{sn-jnl}"),
    ("pnas", r"\documentclass[9pt,twocolumn,twoside]{pnas-new}"),
]


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Provide a writable scratch dir with a minimal references.bib."""
    bib = tmp_path / "references.bib"
    bib.write_text(
        "@article{knutti2008, author = {A}, title = {T}, journal = {J}, year = {2008}}\n"
        "@article{tierney_zhu2020, author = {B}, title = {T2}, journal = {J}, year = {2020}}\n"
    )
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.mark.parametrize("template,expected", TEMPLATES)
def test_template_renders(template, expected, workdir):
    md = workdir / "example.md"
    short = "cp" if template == "copernicus" else ""
    md.write_text(SAMPLE_MD.format(template=template, short=short))

    tex_path = workdir / "build" / f"{template}.tex"
    build_tex(
        str(md),
        str(tex_path),
        bib_file=str(workdir / "references.bib"),
        build_dir=str(workdir / "build"),
        journal_template=template,
    )

    tex = tex_path.read_text()
    assert expected in tex, (
        f"Expected fragment {expected!r} not found in rendered tex for "
        f"template={template}. First 400 chars:\n{tex[:400]}"
    )


def test_force_cite_applied_for_science(workdir):
    """Science template forces all citations to \\cite{} (numbered)."""
    md = workdir / "example.md"
    md.write_text(SAMPLE_MD.format(template="science", short=""))

    tex_path = workdir / "build" / "science.tex"
    build_tex(
        str(md),
        str(tex_path),
        bib_file=str(workdir / "references.bib"),
        build_dir=str(workdir / "build"),
        journal_template="science",
    )

    tex = tex_path.read_text()
    # both @key and [@key] should have been rewritten to \cite{}
    assert r"\cite{knutti2008}" in tex
    assert r"\cite{tierney_zhu2020}" in tex
    # natbib in-text form should NOT appear (force_cite strips it)
    assert r"\citet{" not in tex


def test_apacite_cite_applied_for_agu(workdir):
    """AGU template rewrites \\citet -> \\citeA and \\citep -> \\cite (apacite)."""
    md = workdir / "example.md"
    md.write_text(SAMPLE_MD.format(template="agujournal", short=""))

    tex_path = workdir / "build" / "agu.tex"
    build_tex(
        str(md),
        str(tex_path),
        bib_file=str(workdir / "references.bib"),
        build_dir=str(workdir / "build"),
        journal_template="agujournal",
    )

    tex = tex_path.read_text()
    # in-text @key becomes \citeA{}
    assert r"\citeA{tierney_zhu2020}" in tex
    # parenthetical [@key] becomes plain \cite{}
    assert r"\cite{knutti2008}" in tex
    # natbib commands should NOT survive as actual citations
    # (the template header has \citet{key} / \citep{key} in a comment block,
    # so check for the actual cite keys instead of the bare command)
    assert r"\citet{tierney_zhu2020}" not in tex
    assert r"\citet{knutti2008}" not in tex
    assert r"\citep{knutti2008}" not in tex
