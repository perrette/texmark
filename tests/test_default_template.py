"""The default template (no ``journal`` in the front matter) builds."""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import main
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")

DOC = """\
---
title: A default paper
authors:
  - firstname: Ada
    lastname: Lovelace
abstract: A short abstract.
bibliography: refs.bib
---

# Introduction

Hello, as shown by @k2020.
"""

BIB = "@article{k2020,\n  author = {Doe, J.},\n  title = {A title},\n  journal = {J. Tests},\n  year = {2020}\n}\n"


@pytest.fixture
def doc(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    (tmp_path / "doc.md").write_text(DOC)
    (tmp_path / "refs.bib").write_text(BIB)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _build(doc_dir, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["texmark", str(doc_dir / "doc.md"), "-d", str(doc_dir / "build"), *extra])
    main()
    return doc_dir / "build"


def test_default_template_builds_tex(doc, monkeypatch):
    out = (_build(doc, monkeypatch) / "doc.tex").read_text()
    assert "\\title{ A default paper }" in out
    assert "\\author{Ada Lovelace}" in out
    assert "\\begin{abstract}\nA short abstract." in out
    assert "\\graphicspath{{../images/}}" in out
    assert "\\bibliographystyle{plainnat}" in out
    assert "\\bibliography{refs.bib}" in out
    assert "{ {" not in out and "}}}" not in out  # no stray Jinja leftovers


def test_default_template_extra_packages(doc, monkeypatch):
    out = (_build(doc, monkeypatch, "--packages", "siunitx") / "doc.tex").read_text()
    assert "\\usepackage{ siunitx }" in out


def test_default_template_skips_already_loaded_packages(doc, monkeypatch):
    out = (_build(doc, monkeypatch, "--packages", "natbib", "hyperref", "siunitx") / "doc.tex").read_text()
    assert out.count("{natbib}") == 1 and "{ natbib }" not in out
    assert "{ hyperref }" not in out
    assert "\\usepackage{ siunitx }" in out


@pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                    reason="latexmk/pdflatex not available")
def test_default_template_builds_pdf(doc, monkeypatch):
    build = _build(doc, monkeypatch, "--pdf")
    assert (build / "doc.pdf").read_bytes()[:4] == b"%PDF"
    log = (build / "doc.log").read_text()
    assert "undefined" not in log
