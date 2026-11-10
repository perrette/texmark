"""compile_pdf with a real LaTeX toolchain: the jobname PDF, publishing the
output PDF, and the tex-only build directory.

Skips when pandoc, latexmk or pdflatex is missing.
"""
import os
import shutil
import sys
from pathlib import Path

import pytest

from texmark.build import main
from tests import pandoc_available


REPO_ROOT = Path(__file__).parent.parent

pytestmark = pytest.mark.skipif(
    not pandoc_available(),
    reason="pandoc not available (install pypandoc_binary or system pandoc)",
)

needs_latexmk = pytest.mark.skipif(
    shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
    reason="latexmk/pdflatex not on PATH",
)


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    """Ensure pandoc subprocess filters import this checkout's texmark."""
    existing = os.environ.get("PYTHONPATH", "")
    new_path = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
    monkeypatch.setenv("PYTHONPATH", new_path)


DOC = """---
title: Test
journal:
  template: default
---

# Intro {#sec:intro}

See Section \\ref{sec:intro}.
"""


def _texmark(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["texmark", *map(str, argv)])
    main()


def _write_doc(tmp_path, text=DOC):
    src = tmp_path / "doc.md"
    src.write_text(text)
    return src


@needs_latexmk
def test_job_pdf_kept_and_unchanged_build_skips_engine(tmp_path, monkeypatch, capfd):
    """With -o differing from the jobname, the jobname PDF stays in the build
    directory, so a second build of unchanged sources does not rerun pdflatex."""
    monkeypatch.chdir(tmp_path)
    src = _write_doc(tmp_path)
    build = tmp_path / "build"
    out = build / "out.pdf"

    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out)
    assert out.exists()
    assert (build / "doc.pdf").exists()
    log_mtime = (build / "doc.log").stat().st_mtime_ns

    capfd.readouterr()
    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out)
    captured = capfd.readouterr()
    assert "Nothing to do" in captured.out + captured.err
    assert (build / "doc.log").stat().st_mtime_ns == log_mtime


@needs_latexmk
def test_output_pdf_replaced_atomically(tmp_path, monkeypatch):
    """The output PDF is renamed into place (new inode) and no temporary
    file is left next to it."""
    monkeypatch.chdir(tmp_path)
    src = _write_doc(tmp_path)
    build = tmp_path / "build"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    out = out_dir / "paper.pdf"

    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out)
    inode = out.stat().st_ino
    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out)
    assert out.stat().st_ino != inode
    assert out.read_bytes() == (build / "doc.pdf").read_bytes()
    assert sorted(p.name for p in out_dir.iterdir()) == ["paper.pdf"]
