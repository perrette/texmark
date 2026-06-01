"""Tests for biblatex per-chapter bibliographies (Item 18)."""
import os
import shutil
import sys
from pathlib import Path

import pytest

import texmark.build
from texmark.build import build_tex, compile_pdf, main


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


def _build_single(out_dir, md_text, journal_template=None):
    """Build a single markdown file to its master .tex and return the text."""
    out_dir.mkdir(parents=True, exist_ok=True)
    src = out_dir / "doc.md"
    src.write_text(md_text)
    out_tex = out_dir / "doc.tex"
    build_tex(str(src), str(out_tex), journal_template=journal_template,
              build_dir=str(out_dir))
    return out_tex.read_text()


# --- per-chapter biblatex preamble + refsection wrapping --------------------

def test_per_chapter_emits_biblatex_and_refsections(tmp_path, monkeypatch):
    """Book root with bibliography_per_chapter: true -> biblatex preamble +
    one refsection (with \\printbibliography) per embedded chapter."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "refs.bib").write_text("@article{a, title={A}, author={X}, year={2020}}\n")
    (src / "chapter1.md").write_text("---\ntitle: One\n---\n\n# One\n\nText \\cite{a}.\n")
    (src / "chapter2.md").write_text("---\ntitle: Two\n---\n\n# Two\n\nMore \\cite{a}.\n")
    (src / "root.md").write_text(
        "---\n"
        "title: A Book\n"
        "bibliography: refs.bib\n"
        "bibliography_per_chapter: true\n"
        "journal:\n"
        "  template: book\n"
        "---\n\n"
        "![](chapter1.md)\n\n"
        "![](chapter2.md)\n"
    )

    build_dir = tmp_path / "build"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv",
                        ["texmark", str(src / "root.md"), "-d", str(build_dir)])
    main()

    tex = (build_dir / "root.tex").read_text()
    # biblatex preamble replaces natbib
    assert "\\usepackage[backend=biber,style=authoryear]{biblatex}" in tex
    assert "\\addbibresource{ refs.bib }" in tex
    assert "\\usepackage{natbib}" not in tex
    # no global natbib bibliography when per-chapter
    assert "\\bibliographystyle" not in tex
    # one refsection per chapter, each printing its own bibliography
    assert tex.count("\\begin{refsection}") == 2
    assert tex.count("\\end{refsection}") == 2
    assert tex.count("\\printbibliography[heading=subbibliography]") == 2
    # the includes themselves are still present, inside the refsections
    assert "\\include{chapter1}" in tex
    assert "\\include{chapter2}" in tex


# --- regression: flag off is byte-identical, natbib pipeline intact ---------

def test_flag_off_byte_identical_to_absent(tmp_path):
    """A build with bibliography_per_chapter: false is byte-identical to one
    without the key, and keeps the natbib+bibtex pipeline."""
    base = (
        "---\n"
        "title: T\n"
        "bibliography: refs.bib\n"
        "{flag}"
        "journal:\n"
        "  template: book\n"
        "---\n\n"
        "# Chapter\n\nBody.\n"
    )
    absent = _build_single(tmp_path / "absent", base.format(flag=""))
    false = _build_single(tmp_path / "false",
                          base.format(flag="bibliography_per_chapter: false\n"))

    assert absent == false
    # natbib pipeline is untouched when the flag is off
    assert "\\usepackage{natbib}" in absent
    assert "\\bibliographystyle" in absent
    assert "\\bibliography{ refs.bib }" in absent
    assert "biblatex" not in absent
    assert "refsection" not in absent


# --- non-book-family templates: flag ignored, with a warning ----------------

def test_non_book_family_warns_and_ignores(tmp_path, monkeypatch):
    """An article-class template with the flag set warns and keeps natbib."""
    warnings = []
    monkeypatch.setattr(texmark.build.logger, "warning",
                        lambda msg, *a, **k: warnings.append(msg))

    tex = _build_single(
        tmp_path / "art",
        "---\ntitle: T\nbibliography: refs.bib\n"
        "bibliography_per_chapter: true\n---\n\n# Sec\n\nBody.\n",
        journal_template="arxiv",
    )

    assert any("bibliography_per_chapter requires a book-family template" in m
               for m in warnings)
    # article template keeps natbib; no biblatex / refsection leaks in
    assert "\\usepackage{natbib}" in tex
    assert "biblatex" not in tex
    assert "refsection" not in tex


# --- compile_pdf swaps bibtex -> biber on the raw backend -------------------

def test_compile_pdf_raw_uses_biber_when_biblatex(tmp_path, monkeypatch):
    """The raw backend runs biber (not bibtex) when biblatex=True."""
    build_dir = tmp_path
    tex = build_dir / "doc.tex"
    tex.write_text("\\documentclass{book}\\begin{document}\\end{document}\n")
    # Pre-create the .pdf so compile_pdf's copy step is a no-op against itself.
    pdf = build_dir / "doc.pdf"
    pdf.write_text("%PDF-1.4\n")

    calls = []
    monkeypatch.setattr(texmark.build, "run",
                        lambda cmd, **k: calls.append(cmd))

    compile_pdf(str(tex), str(pdf), build_dir=str(build_dir),
                bib_file="", backend="raw", biblatex=True)

    flat = [tok for cmd in calls for tok in cmd]
    assert "biber" in flat
    assert "bibtex" not in flat


def test_compile_pdf_raw_uses_bibtex_without_biblatex(tmp_path, monkeypatch):
    """Default (biblatex=False) raw backend still runs bibtex."""
    build_dir = tmp_path
    tex = build_dir / "doc.tex"
    tex.write_text("\\documentclass{book}\\begin{document}\\end{document}\n")
    pdf = build_dir / "doc.pdf"
    pdf.write_text("%PDF-1.4\n")

    calls = []
    monkeypatch.setattr(texmark.build, "run",
                        lambda cmd, **k: calls.append(cmd))

    compile_pdf(str(tex), str(pdf), build_dir=str(build_dir),
                bib_file="", backend="raw", biblatex=False)

    flat = [tok for cmd in calls for tok in cmd]
    assert "bibtex" in flat
    assert "biber" not in flat
