"""compile_pdf with a real LaTeX toolchain: the jobname PDF, publishing the
output PDF, and the tex-only build directory.

Skips when pandoc, latexmk or pdflatex is missing.
"""
import os
import re
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


FIG_DOC = """---
title: Test
journal:
  template: default
---

# Intro {#sec:intro}

![A figure](fig.png){#fig:a width=50%}

See Section \\ref{sec:intro}.
"""

PNG = REPO_ROOT / "tests" / "fixtures" / "multifile_figures" / "repo-images" / "foo.png"


def _write_fig_doc(tmp_path, text=FIG_DOC):
    shutil.copy(PNG, tmp_path / "fig.png")
    return _write_doc(tmp_path, text)


def _embeds_figure(build, job):
    """Whether the job's last engine pass put the figure in the PDF. In draft
    mode graphicx still reads the file for its size, but the log has no
    `<use ...fig.png>` line."""
    return re.search(r"<use [^>]*fig\.png>", (build / f"{job}.log").read_text()) is not None


@needs_latexmk
def test_draft_build_uses_separate_job(tmp_path, monkeypatch):
    """--draft compiles the job doc-draft with graphicx's draft option,
    writes the -o PDF, and leaves the full job's files alone."""
    monkeypatch.chdir(tmp_path)
    src = _write_fig_doc(tmp_path)
    build = tmp_path / "build"
    out = build / "out.pdf"

    _texmark(monkeypatch, src, "--pdf", "-d", build, "-o", out)
    assert _embeds_figure(build, "doc")
    full_aux = (build / "doc.aux").stat().st_mtime_ns
    full_pdf = (build / "doc.pdf").read_bytes()

    _texmark(monkeypatch, src, "--pdf", "--draft", "-d", build, "-o", out)
    assert (build / "doc-draft.aux").exists()
    assert "\\PassOptionsToPackage{draft}{graphicx}\\input{doc.tex}" in (build / "doc-draft.log").read_text()
    assert not _embeds_figure(build, "doc-draft")
    assert out.read_bytes() == (build / "doc-draft.pdf").read_bytes()
    assert (build / "doc.aux").stat().st_mtime_ns == full_aux
    assert (build / "doc.pdf").read_bytes() == full_pdf


@needs_latexmk
def test_draft_from_yaml_then_full_build_on_default_output(tmp_path, monkeypatch):
    """YAML draft: true publishes the draft over <build>/doc.pdf (the full
    job's own PDF); the next full build must replace it although latexmk
    alone would find nothing to do."""
    monkeypatch.chdir(tmp_path)
    build = tmp_path / "build"
    src = _write_fig_doc(tmp_path)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    full_pdf = (build / "doc.pdf").read_bytes()

    _write_doc(tmp_path, FIG_DOC.replace("---\n\n#", "draft: true\n---\n\n#"))
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert (build / "doc.pdf").read_bytes() == (build / "doc-draft.pdf").read_bytes()

    _write_doc(tmp_path, FIG_DOC)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert (build / "doc.pdf").read_bytes() != (build / "doc-draft.pdf").read_bytes()
    assert _embeds_figure(build, "doc")
    assert not list(build.glob(".doc.pdf-is-draft"))


def test_draft_raw_backend_command(tmp_path, monkeypatch):
    """The raw backend puts the draft option in the engine's input argument
    and runs bibtex on the draft job's .aux."""
    import texmark.build as B
    tex = tmp_path / "doc.tex"
    tex.write_text("\\documentclass{article}\\begin{document}\\end{document}\n")
    (tmp_path / "doc-draft.pdf").write_text("%PDF-1.4\n")
    calls = []
    monkeypatch.setattr(B, "run", lambda cmd, **k: calls.append(cmd))
    B.compile_pdf(str(tex), str(tmp_path / "out.pdf"), build_dir=str(tmp_path),
                  bib_file="", backend="raw", draft=True)
    assert calls[0] == ["pdflatex", "-interaction=nonstopmode", "-jobname=doc-draft",
                        "\\PassOptionsToPackage{draft}{graphicx}\\input{doc.tex}"]
    assert ["bibtex", "doc-draft.aux"] in calls
    assert (tmp_path / "out.pdf").exists()
