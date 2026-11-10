"""Precompiled preamble (texmark.preamble_format) with a real toolchain.

Skips when pandoc, latexmk, pdflatex or mylatexformat is missing.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from texmark import preamble_format
from texmark.build import main
from tests import pandoc_available


REPO_ROOT = Path(__file__).parent.parent

pytestmark = [
    pytest.mark.skipif(not pandoc_available(),
                       reason="pandoc not available"),
    pytest.mark.skipif(shutil.which("latexmk") is None or shutil.which("pdflatex") is None,
                       reason="latexmk/pdflatex not on PATH"),
    pytest.mark.skipif(not preamble_format.mylatexformat_path(),
                       reason="mylatexformat.ltx not installed"),
]

needs_pdftotext = pytest.mark.skipif(shutil.which("pdftotext") is None,
                                     reason="pdftotext not on PATH")


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + (os.pathsep + existing if existing else ""))


DOC = """---
title: Test
journal:
  template: default
preamble: |
  \\usepackage{mysty}
  \\usepackage{xcolor}
---

# Intro {#sec:intro}

\\mystymacro{} See Section \\ref{sec:intro}.
"""

STY = "\\ProvidesPackage{mysty}\n\\newcommand\\mystymacro{STYTEXT-%s}\n"


def _texmark(monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["texmark", *map(str, argv)])
    main()


def _setup(tmp_path, monkeypatch, text=DOC):
    monkeypatch.chdir(tmp_path)
    src = tmp_path / "doc.md"
    src.write_text(text)
    build = tmp_path / "build"
    build.mkdir()
    (build / "mysty.sty").write_text(STY % "one")
    return src, build


def _fmt_mtime(build):
    return (build / "doc-preamble.fmt").stat().st_mtime_ns


def _used_format(build, job="doc"):
    log = (build / f"{job}.log").read_text(errors="replace")
    return "(mylatexformat)Info: start reading document" in log


def _pdftext(pdf):
    return subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout


def test_format_created_and_reused(tmp_path, monkeypatch, capfd):
    src, build = _setup(tmp_path, monkeypatch)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert (build / "doc-preamble.fmt").exists()
    assert _used_format(build)
    first = _fmt_mtime(build)

    # Unchanged: the format is not rebuilt and latexmk has nothing to do.
    capfd.readouterr()
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    out = capfd.readouterr()
    assert "Nothing to do" in out.out + out.err
    assert _fmt_mtime(build) == first

    # Body-only change: same format, new PDF.
    src.write_text(DOC.replace("See Section", "BODYCHANGE See Section"))
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert _fmt_mtime(build) == first
    assert _used_format(build)
    assert "BODYCHANGE" in (build / "doc.tex").read_text()


@needs_pdftotext
def test_local_sty_change_rebuilds_format(tmp_path, monkeypatch):
    """A file loaded into the format is not in the run's .fls: the format
    key covers it, and the rebuilt format makes latexmk rerun."""
    src, build = _setup(tmp_path, monkeypatch)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    first = _fmt_mtime(build)
    assert "STYTEXT-one" in _pdftext(build / "doc.pdf")

    (build / "mysty.sty").write_text(STY % "two")
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert _fmt_mtime(build) != first
    assert "STYTEXT-two" in _pdftext(build / "doc.pdf")


def test_preamble_change_rebuilds_format(tmp_path, monkeypatch):
    src, build = _setup(tmp_path, monkeypatch)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    first = _fmt_mtime(build)
    src.write_text(DOC.replace("\\usepackage{xcolor}", "\\usepackage{xcolor}\n  \\usepackage{booktabs}"))
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert _fmt_mtime(build) != first
    assert _used_format(build)


def test_preamble_file_change_rebuilds_format(tmp_path, monkeypatch):
    """A preamble given as a file (YAML ``preamble: preamble.tex``)."""
    text = DOC.replace("preamble: |\n  \\usepackage{mysty}\n  \\usepackage{xcolor}",
                       "preamble: preamble.tex")
    src, build = _setup(tmp_path, monkeypatch, text)
    (tmp_path / "preamble.tex").write_text("\\usepackage{mysty}\n")
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    first = _fmt_mtime(build)
    (tmp_path / "preamble.tex").write_text("\\usepackage{mysty}\n\\usepackage{xcolor}\n")
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert _fmt_mtime(build) != first


FIG_DOC = DOC + """
![A figure](fig.png){#fig:a width=50%}
"""

PNG = REPO_ROOT / "tests" / "fixtures" / "multifile_figures" / "repo-images" / "foo.png"


def test_draft_job_uses_format_and_draft_boxes(tmp_path, monkeypatch, caplog):
    src, build = _setup(tmp_path, monkeypatch, FIG_DOC)
    shutil.copy(PNG, tmp_path / "fig.png")
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build, "--draft")
    out = caplog.text
    assert "-usepretex" not in out
    assert _used_format(build, "doc-draft")
    assert "<use " not in (build / "doc-draft.log").read_text(errors="replace")
    assert (build / "doc-draft.pdf").exists()

    # The full job, from the same format, includes the figure.
    first = _fmt_mtime(build)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert _fmt_mtime(build) == first
    assert _used_format(build)
    assert "<use " in (build / "doc.log").read_text(errors="replace")


ROOT = """---
title: Main
journal:
  template: default
companions:
  - si.md
---

# Intro

See Section [S](si.md#sec:target).
"""

SI = """---
title: SI
journal:
  template: default
---

# First {#sec:first}

%s
# Target {#sec:target}

Text.
"""


@needs_pdftotext
def test_companion_labels_are_read_on_each_run(tmp_path, monkeypatch):
    """\\externaldocument comes after the preamble marker, so a run with
    the format imports the companion's current labels."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "main.md").write_text(ROOT)
    (tmp_path / "si.md").write_text(SI % "")
    build = tmp_path / "build"
    _texmark(monkeypatch, tmp_path / "main.md", "--pdf", "-d", build)
    assert _used_format(build, "main")
    assert "See Section 2" in _pdftext(build / "main.pdf")

    (tmp_path / "si.md").write_text(SI % "# Inserted\n\n")
    _texmark(monkeypatch, tmp_path / "main.md", "--pdf", "-d", build)
    assert _used_format(build, "main")
    assert "See Section 3" in _pdftext(build / "main.pdf")


def test_no_mylatexformat_falls_back(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(preamble_format, "mylatexformat_path", lambda: "")
    src, build = _setup(tmp_path, monkeypatch)
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    out = caplog.text
    assert "-fmt=" not in out
    assert not (build / "doc-preamble.fmt").exists()
    assert (build / "doc.pdf").exists()
    assert not _used_format(build)


def test_format_run_failure_falls_back_and_is_remembered(tmp_path, monkeypatch, caplog):
    src, build = _setup(tmp_path, monkeypatch)
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert _used_format(build)

    # An unloadable format ("Fatal format file error"): the engine writes no
    # log, the run is repeated without the format.
    (build / "doc-preamble.fmt").write_bytes(b"not a format")
    src.write_text(DOC.replace("See Section", "AFTERFAIL See Section"))
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    out = caplog.text
    assert "without it" in out
    assert not _used_format(build)
    assert "AFTERFAIL" in (build / "doc.tex").read_text()
    assert (build / "doc.pdf").stat().st_mtime_ns >= (build / "doc.tex").stat().st_mtime_ns

    # Remembered: the next build does not try the format again.
    src.write_text(DOC.replace("See Section", "AGAIN See Section"))
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    out = caplog.text
    assert "-fmt=" not in out


def test_format_build_failure_falls_back(tmp_path, monkeypatch, caplog):
    src, build = _setup(tmp_path, monkeypatch)
    (build / "mysty.sty").write_text("\\ProvidesPackage{mysty}\n\\undefinedcommandxyz\n"
                                     "\\newcommand\\mystymacro{}\n")
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    out = caplog.text
    assert "building the precompiled preamble failed" in out
    assert not (build / "doc-preamble.fmt").exists()
    assert (build / "doc.pdf").exists()

    # Fixed: the format is built.
    (build / "mysty.sty").write_text(STY % "fixed")
    _texmark(monkeypatch, src, "--pdf", "-d", build)
    assert (build / "doc-preamble.fmt").exists()
    assert _used_format(build)


@pytest.mark.parametrize("how", ["cli", "yaml"])
def test_opt_out(tmp_path, monkeypatch, caplog, how):
    text = DOC if how == "cli" else DOC.replace("title: Test", "title: Test\nbuild_preamble_format: false")
    src, build = _setup(tmp_path, monkeypatch, text)
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build,
             *(["--no-preamble-format"] if how == "cli" else []))
    out = caplog.text
    assert "-fmt=" not in out
    assert not (build / "doc-preamble.fmt").exists()
    assert not _used_format(build)


def test_raw_backend_uses_format(tmp_path, monkeypatch, caplog):
    src, build = _setup(tmp_path, monkeypatch)
    caplog.clear()
    _texmark(monkeypatch, src, "--pdf", "-d", build, "--backend", "raw")
    out = caplog.text
    assert "pdflatex -fmt=doc-preamble" in out
    assert _used_format(build)


def test_progressive_uses_format(tmp_path, monkeypatch):
    src, build = _setup(tmp_path, monkeypatch, FIG_DOC)
    shutil.copy(PNG, tmp_path / "fig.png")
    _texmark(monkeypatch, src, "--pdf", "-d", build, "--progressive")
    assert _used_format(build, "doc-draft")
    assert _used_format(build)
    assert "<use " not in (build / "doc-draft.log").read_text(errors="replace")
    assert "<use " in (build / "doc.log").read_text(errors="replace")
