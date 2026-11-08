"""Back-matter statements in the science template."""
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import build_tex, main
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)


def _md(extra=""):
    lines = ["---", "title: T",
             "authors:", "  - firstname: Ann", "    lastname: One", "    email: ann@x.org",
             "    affiliation: 1", "    corresponding: true",
             "affiliations:", "  - Inst A"]
    if extra:
        lines.append(extra)
    lines += ["---", "", "# Introduction", "", "Hello.", ""]
    return "\n".join(lines)


def _build(tmp_path, monkeypatch, md_text):
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "doc.md"
    md.write_text(md_text)
    tex_path = tmp_path / "build" / "doc.tex"
    build_tex(str(md), str(tex_path), build_dir=str(tmp_path / "build"), journal_template="science")
    return tex_path.read_text()


def test_dataavailability_paragraph(tmp_path, monkeypatch):
    tex = _build(tmp_path, monkeypatch, _md("dataavailability: Data are on Zenodo."))
    assert "\\paragraph*{Data and materials availability:}\nData are on Zenodo." in tex
    assert r"\dataavailability" not in tex


def test_dataavailability_placeholder_when_unset(tmp_path, monkeypatch):
    tex = _build(tmp_path, monkeypatch, _md())
    assert "\\paragraph*{Data and materials availability:}\nplease add a \"data availability\" section" in tex
    assert r"\dataavailability" not in tex


@pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                    reason="latexmk/pdflatex not available")
def test_dataavailability_builds_pdf(tmp_path, monkeypatch):
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""))
    monkeypatch.chdir(tmp_path)
    md = tmp_path / "doc.md"
    md.write_text(_md("acknowledgements: Thanks.\ndataavailability: Data are on Zenodo."))
    build_dir = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["texmark", str(md), "-j", "science", "-d", str(build_dir), "--pdf"])
    main()
    assert (build_dir / "doc.pdf").read_bytes()[:4] == b"%PDF"
    log = (build_dir / "doc.log").read_text(errors="replace")
    errors = re.findall(r"^! .*?^l\.\d+ .*?$", log, re.M | re.S)
    assert not errors, errors
