"""``bibliography:`` may be a list of .bib files, as in pandoc."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import main, bib_files, _collect_watch_paths
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")

DOC = """\
---
title: Two bibs
bibliography: [a.bib, b.bib]
---

# Introduction

See @a2020 and @b2021.
"""

BIB_A = "@article{a2020,\n  author = {Doe, J.},\n  title = {First},\n  journal = {J. Tests},\n  year = {2020}\n}\n"
BIB_B = "@article{b2021,\n  author = {Roe, R.},\n  title = {Second},\n  journal = {J. Tests},\n  year = {2021}\n}\n"


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    (tmp_path / "doc.md").write_text(DOC)
    (tmp_path / "a.bib").write_text(BIB_A)
    (tmp_path / "b.bib").write_text(BIB_B)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _build(doc_dir, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["texmark", str(doc_dir / "doc.md"), "-d", str(doc_dir / "build"), *extra])
    main()
    return doc_dir / "build"


def test_bib_files():
    assert bib_files(None) == []
    assert bib_files("") == []
    assert bib_files("refs.bib") == ["refs.bib"]
    assert bib_files(["a.bib", "b.bib"]) == ["a.bib", "b.bib"]


@pytest.mark.parametrize("journal", ["default", "arxiv"])
def test_bibliography_list_tex(doc, monkeypatch, journal):
    build = _build(doc, monkeypatch, "-j", journal)
    out = (build / "doc.tex").read_text()
    assert "a.bib,b.bib" in out.replace(" ", "")
    assert "[" not in out.split("\\bibliography{", 1)[1].split("}", 1)[0]
    # citations from both files are resolved by pandoc into \cite commands
    assert "a2020" in out and "b2021" in out
    # both files are staged next to the .tex in a tex-only build
    assert (build / "a.bib").exists() and (build / "b.bib").exists()


def test_bibliography_list_watch_paths(doc, monkeypatch):
    from texmark.build import plan_project, _build_parser
    monkeypatch.setattr(sys, "argv", ["texmark", str(doc / "doc.md"), "-d", str(doc / "build")])
    plan = plan_project(_build_parser().parse_args())
    paths = [str(p) for p in _collect_watch_paths(plan, {"bibliography": ["a.bib", "b.bib"]})]
    assert "a.bib" in paths and "b.bib" in paths


@pytest.mark.skipif(not (shutil.which("latexmk") and shutil.which("pdflatex") and shutil.which("bibtex")),
                    reason="latexmk/pdflatex/bibtex not available")
@pytest.mark.parametrize("journal", ["default", "arxiv"])
def test_bibliography_list_pdf(doc, monkeypatch, journal):
    build = _build(doc, monkeypatch, "-j", journal, "--pdf")
    assert (build / "doc.pdf").exists()
    bbl = (build / "doc.bbl").read_text()
    assert "a2020" in bbl and "b2021" in bbl
