"""SyncTeX: the .synctex.gz written by the LaTeX runs and published next to
the PDF (docs/synctex-design.md).

Skips when pandoc, latexmk or pdflatex is missing; the tests that run the
synctex binary skip when it is missing.
"""
import gzip
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import texmark.build as B
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    not pandoc_available() or shutil.which("latexmk") is None
    or shutil.which("pdflatex") is None,
    reason="pandoc, latexmk or pdflatex missing",
)

needs_synctex = pytest.mark.skipif(shutil.which("synctex") is None,
                                   reason="synctex not on PATH")


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + (os.pathsep + existing if existing else ""))


DOC = """---
title: Test
journal:
  template: default
---

# Intro {#sec:intro}

A first paragraph with enough words to fill a line, written on
two lines of the Markdown source.

Second paragraph.
"""


def _texmark(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["texmark", *map(str, argv)])
    B.main()


def _doc(tmp_path, text=DOC):
    src = tmp_path / "doc.md"
    src.write_text(text)
    return src


def _synctex_page(pdf, tex, pattern):
    """The page that ``synctex view`` gives for the first line of ``tex``
    matching ``pattern``, or None."""
    lines = Path(tex).read_text().splitlines()
    line = next(i for i, l in enumerate(lines, 1) if re.search(pattern, l))
    out = subprocess.run(
        ["synctex", "view", "-i", f"{line}:1:{Path(tex).resolve()}", "-o", str(pdf)],
        capture_output=True, text=True).stdout
    m = re.search(r"^Page:(\d+)", out, re.M)
    return int(m.group(1)) if m else None


def _synctex_text(gz):
    """The content of a .synctex.gz; a complete one ends with a postamble."""
    return gzip.open(gz, "rt", errors="replace").read()


@pytest.mark.parametrize("backend", ["latexmk", "raw"])
def test_synctex_next_to_default_pdf(tmp_path, monkeypatch, backend):
    monkeypatch.chdir(tmp_path)
    build = tmp_path / "build"
    _texmark(monkeypatch, _doc(tmp_path), "--pdf", "-d", build, "-b", backend)
    assert (build / "doc.pdf").exists()
    assert "Postamble:" in _synctex_text(build / "doc.synctex.gz")


@needs_synctex
def test_synctex_follows_renamed_pdf(tmp_path, monkeypatch):
    """With -o, the synctex file is published as <out-stem>.synctex.gz and
    synctex finds it from the published PDF."""
    monkeypatch.chdir(tmp_path)
    build, out = tmp_path / "build", tmp_path / "out" / "paper.pdf"
    out.parent.mkdir()
    _texmark(monkeypatch, _doc(tmp_path), "--pdf", "-d", build, "-o", out)
    assert (out.parent / "paper.synctex.gz").read_bytes() == \
        (build / "doc.synctex.gz").read_bytes()
    assert _synctex_page(out, build / "doc.tex", "Second paragraph") == 1


@needs_synctex
def test_draft_synctex_published(tmp_path, monkeypatch):
    """--draft publishes the draft job's synctex file with its PDF, also on
    the default path (the full job's own name)."""
    monkeypatch.chdir(tmp_path)
    build = tmp_path / "build"
    _texmark(monkeypatch, _doc(tmp_path), "--pdf", "--draft", "-d", build)
    assert (build / "doc.synctex.gz").read_bytes() == \
        (build / "doc-draft.synctex.gz").read_bytes()
    assert _synctex_page(build / "doc.pdf", build / "doc.tex", "Second paragraph") == 1


def test_progressive_publishes_matching_synctex(tmp_path, monkeypatch):
    """--progressive: each stage publishes its job's synctex file before the
    PDF; after the last stage, the published pair is the full job's."""
    monkeypatch.chdir(tmp_path)
    build, out = tmp_path / "build", tmp_path / "paper.pdf"
    published = []
    real = B.publish_file

    def recording(src, dst):
        published.append((Path(src).name, Path(dst).name))
        real(src, dst)

    monkeypatch.setattr(B, "publish_file", recording)
    _texmark(monkeypatch, _doc(tmp_path), "--pdf", "--progressive", "-d", build, "-o", out)
    assert published == [
        ("doc-draft.synctex.gz", "paper.synctex.gz"), ("doc-draft.pdf", "paper.pdf"),
        ("doc.synctex.gz", "paper.synctex.gz"), ("doc.pdf", "paper.pdf"),
    ]
    assert (tmp_path / "paper.synctex.gz").read_bytes() == \
        (build / "doc.synctex.gz").read_bytes()


def test_no_synctex(tmp_path, monkeypatch):
    """--no-synctex writes no synctex file and removes the one published by
    an earlier build, which would describe another PDF."""
    monkeypatch.chdir(tmp_path)
    build, out = tmp_path / "build", tmp_path / "paper.pdf"
    src = _doc(tmp_path)
    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out)
    assert (tmp_path / "paper.synctex.gz").exists()
    src.write_text(DOC + "\nThird paragraph.\n")
    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out, "--no-synctex")
    assert not (tmp_path / "paper.synctex.gz").exists()
    assert not (build / "doc.synctex.gz").exists()


def test_publish_without_job_synctex_removes_stale_one(tmp_path):
    """A job that wrote no synctex file (e.g. an engine that failed early)
    does not leave the previous one next to the new PDF."""
    build = tmp_path / "build"
    build.mkdir()
    (build / "doc-draft.pdf").write_bytes(b"%PDF new")
    out = tmp_path / "paper.pdf"
    (tmp_path / "paper.synctex.gz").write_bytes(b"old")
    B.publish_job_pdf(build / "doc.tex", out, build, draft=True)
    assert out.read_bytes() == b"%PDF new"
    assert not (tmp_path / "paper.synctex.gz").exists()
