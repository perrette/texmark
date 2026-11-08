"""documentclassoptions in the YAML reaches \\documentclass in the
book-family templates (report/book/memoir/classicthesis)."""
import os
import sys
from pathlib import Path

import pytest

from texmark.build import main
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(not pandoc_available(), reason="pandoc not available")

TEMPLATES = [
    ("report", "report", "11pt,a4paper"),
    ("book", "book", "11pt,a4paper,openright"),
    ("memoir", "memoir", "11pt,a4paper,openright"),
    ("classicthesis", "scrreprt",
     "twoside,openright,titlepage,numbers=noenddot,headinclude,a4paper,11pt,BCOR=5mm,DIV=12"),
]


def _build(tmp_path, monkeypatch, journal, extra_yaml=""):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    md = tmp_path / "doc.md"
    md.write_text(f"---\ntitle: T\n{extra_yaml}---\n\n# Introduction\n\nHello.\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-j", journal, "-d", str(tmp_path / "build")])
    main()
    return (tmp_path / "build" / "doc.tex").read_text()


@pytest.mark.parametrize("journal,cls,default", TEMPLATES)
def test_documentclass_default_options(tmp_path, monkeypatch, journal, cls, default):
    out = _build(tmp_path, monkeypatch, journal)
    assert f"\\documentclass[{default}]{{{cls}}}" in out
    assert "$if(" not in out and "$endif$" not in out


@pytest.mark.parametrize("journal,cls,default", TEMPLATES)
def test_documentclass_options_from_yaml(tmp_path, monkeypatch, journal, cls, default):
    out = _build(tmp_path, monkeypatch, journal, "documentclassoptions: 12pt,letterpaper\n")
    assert f"\\documentclass[12pt,letterpaper]{{{cls}}}" in out


@pytest.mark.parametrize("journal,cls,default", TEMPLATES)
def test_documentclass_options_list(tmp_path, monkeypatch, journal, cls, default):
    out = _build(tmp_path, monkeypatch, journal, "documentclassoptions: [12pt, letterpaper]\n")
    assert f"\\documentclass[12pt,letterpaper]{{{cls}}}" in out
