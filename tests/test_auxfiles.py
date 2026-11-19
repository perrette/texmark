"""Incomplete .aux files (texmark.auxfiles): the checks, and builds that start
from an .aux cut short.

The LaTeX tests skip when pandoc, latexmk or pdflatex is missing.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import texmark.build as B
from texmark import auxfiles
from tests import pandoc_available

REPO_ROOT = Path(__file__).parent.parent

needs_latex = pytest.mark.skipif(
    not pandoc_available() or shutil.which("latexmk") is None
    or shutil.which("pdflatex") is None or shutil.which("pdftotext") is None,
    reason="pandoc, latexmk, pdflatex or pdftotext missing",
)


@pytest.fixture(autouse=True)
def _local_texmark_on_pythonpath(monkeypatch):
    existing = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(REPO_ROOT) + (os.pathsep + existing if existing else ""))


MAIN = ("\\relax \n\\providecommand\\hyper@newdestlabel[2]{}\n"
        "\\@input{ch1.aux}\n\\newlabel{x}{{1}{2}{A \\{brace\\} 50\\%}{x}{}}\n"
        "\\gdef \\@abspage@last{3}\n")
CHAPTER = ("\\relax \n\\newlabel{sec:a}{{1}{1}{Intro}{chapter.1}{}}\n"
           "\\@setckpt{ch1}{\n\\setcounter{page}{2}\n\\setcounter{chapter}{1}\n}\n")


def test_valid_files_pass():
    assert auxfiles.aux_problem(MAIN) is None
    assert auxfiles.aux_problem(CHAPTER, chapter=True) is None
    assert auxfiles.aux_problem(CHAPTER) is None
    # an older kernel (no \@abspage@last), or a run that ended with an error
    assert auxfiles.aux_problem("\\relax \n\\newlabel{x}{{1}{2}}\n") is None


@pytest.mark.parametrize("text, chapter", [
    (MAIN[:40], False),                        # mid-line
    (MAIN.replace("{x}{}}\n", "{x}{\n"), False),   # unbalanced
    (MAIN + "\\newlabel{y}{{2}{3}}\n", False),  # \@abspage@last not last
    (CHAPTER[:60], True),
    (CHAPTER.split("\\@setckpt")[0], True),    # complete lines, no \@setckpt
    (CHAPTER[:-2] + "\n", True),               # \@setckpt not closed
    ("", False),
])
def test_incomplete_files_fail(text, chapter):
    assert auxfiles.aux_problem(text, chapter) is not None


def test_check_restores_from_snapshot_or_deletes(tmp_path, caplog):
    import logging
    (tmp_path / "doc.aux").write_text(MAIN)
    (tmp_path / "ch1.aux").write_text(CHAPTER[:60])
    (tmp_path / "ch2.aux").write_text(CHAPTER.replace("ch1", "ch2")[:60])
    (tmp_path / "doc.aux").write_text(MAIN.replace("\\@input{ch1.aux}",
                                                   "\\@input{ch1.aux}\n\\@input{ch2.aux}"))
    snap = tmp_path / auxfiles.SNAPSHOT_DIR
    snap.mkdir()
    (snap / "ch1.aux").write_text(CHAPTER)
    before = (tmp_path / "doc.aux").stat().st_mtime_ns
    with caplog.at_level(logging.INFO, logger="texmark"):
        bad = auxfiles.check_aux_files(tmp_path)
    assert sorted(bad) == ["ch1.aux", "ch2.aux"]
    assert (tmp_path / "ch1.aux").read_text() == CHAPTER
    assert not (tmp_path / "ch2.aux").exists()
    assert (tmp_path / "doc.aux").stat().st_mtime_ns == before
    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 2 and all("incomplete" in m for m in messages)


def test_runaway_aux_names_the_open_aux(tmp_path):
    log = tmp_path / "doc.log"
    log.write_text("(./doc.aux (./ch1.aux) (./ch2.aux\nRunaway argument?\n"
                   "! File ended while scanning use of \\@newl@bel.\n")
    assert auxfiles.runaway_aux(log) == [tmp_path / "ch2.aux"]
    # an error of the document itself, after the .aux files were read
    log.write_text("(./doc.aux (./ch1.aux) (./ch2.aux)) (./ch2.tex\n"
                   "! File ended while scanning use of \\textbf.\n")
    assert auxfiles.runaway_aux(log) == []
    log.write_text("(./doc.aux (./ch1.aux))\nRunaway argument?\n"
                   "! Paragraph ended before \\textbf was complete.\n")
    assert auxfiles.runaway_aux(log) == []


# ---------------------------------------------------------------------------
# builds
# ---------------------------------------------------------------------------

def _book(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "root.md").write_text(
        "---\ntitle: A Book\njournal:\n  template: book\n"
        "chapters: [ch1.md, ch2.md, ch3.md]\n---\n")
    (src / "ch1.md").write_text("# One {#sec:one}\n\nSee Section \\ref{sec:s150}.\n")
    (src / "ch2.md").write_text("# Two {#sec:two}\n\n" + "".join(
        f"## Section {k} {{#sec:s{k}}}\n\nText {k}.\n\n" for k in range(300)))
    (src / "ch3.md").write_text("# Three {#sec:three}\n\nSee Section \\ref{sec:s299}.\n")
    return src


def _texmark(monkeypatch, src, build, *args):
    monkeypatch.chdir(src)
    monkeypatch.setattr(sys, "argv", ["texmark", "root.md", "--pdf", "-d", str(build),
                                      "-o", str(build / "out.pdf"), *args])
    B.main()


def _pdftext(pdf):
    return subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout


def _cut(aux, where):
    """``aux`` cut at 12288 bytes (a real case) or inside the arguments of
    the first \\newlabel after that (TeX then stops with "File ended while
    scanning use of ...")."""
    if where == "12288":
        return aux[:12288]
    return aux[:aux.index(b"\\newlabel", 12288) + len(b"\\newlabel{sec:")]


def _no_runaway(build):
    return all("File ended" not in f.read_text(errors="replace")
               for f in build.glob("*.log"))


@needs_latex
@pytest.mark.parametrize("mode", ["one-off", "progressive"])
@pytest.mark.parametrize("where", ["12288", "in-label"])
def test_truncated_chapter_aux(tmp_path, monkeypatch, mode, where):
    """A chapter .aux cut at 12288 bytes (a real case) is deleted before the
    run, and the build succeeds with every reference resolved."""
    src = _book(tmp_path)
    build = tmp_path / "build"
    args = ["--progressive"] if mode == "progressive" else []
    _texmark(monkeypatch, src, build, *args)
    aux = (build / "ch2.aux").read_bytes()
    assert len(aux) > 12288 and auxfiles.check_aux_files(build) == []
    (build / "ch2.aux").write_bytes(_cut(aux, where))
    (src / "ch1.md").write_text("# One {#sec:one}\n\nEdited. See Section \\ref{sec:s150}.\n")
    _texmark(monkeypatch, src, build, *args)
    assert _no_runaway(build)
    text = _pdftext(build / "out.pdf")
    assert "Edited" in text and "??" not in text
    assert auxfiles.check_aux_files(build) == []


@needs_latex
def test_truncated_main_aux(tmp_path, monkeypatch):
    src = _book(tmp_path)
    build = tmp_path / "build"
    _texmark(monkeypatch, src, build, "--progressive")
    aux = (build / "root-draft.aux").read_bytes()
    (build / "root-draft.aux").write_bytes(aux[:len(aux) // 2 + 7])
    (src / "ch1.md").write_text("# One {#sec:one}\n\nEdited. See Section \\ref{sec:s150}.\n")
    _texmark(monkeypatch, src, build, "--progressive")
    assert _no_runaway(build)
    text = _pdftext(build / "out.pdf")
    assert "Edited" in text and "??" not in text


@needs_latex
def test_runaway_safety_net_reruns(tmp_path, monkeypatch, caplog):
    """When an incomplete .aux gets past the checks (here: checks turned off),
    the pass that fails on it deletes it and runs once more."""
    import logging
    src = _book(tmp_path)
    build = tmp_path / "build"
    _texmark(monkeypatch, src, build)
    aux = (build / "ch2.aux").read_bytes()
    (build / "ch2.aux").write_bytes(_cut(aux, "in-label"))
    monkeypatch.setattr(auxfiles, "check_aux_files", lambda build_dir: [])
    tex = (build / "root.tex").name
    with caplog.at_level(logging.INFO, logger="texmark"):
        ok = B.engine_pass(tex, build, jobname="root-draft")
    assert ok
    assert any("stopped on the incomplete" in r.getMessage() for r in caplog.records)
    assert "\\@setckpt{ch2}" in (build / "ch2.aux").read_text()


@needs_latex
def test_valid_aux_files_untouched(tmp_path, monkeypatch):
    """After normal builds (full, draft, part of chapters), no .aux is
    touched by the check."""
    src = _book(tmp_path)
    build = tmp_path / "build"
    _texmark(monkeypatch, src, build, "--progressive")
    mtimes = {f.name: f.stat().st_mtime_ns for f in build.glob("*.aux")}
    assert len(mtimes) >= 5
    assert auxfiles.check_aux_files(build) == []
    assert {f.name: f.stat().st_mtime_ns for f in build.glob("*.aux")} == mtimes


# ---------------------------------------------------------------------------
# .aux files of another document class or package set
# ---------------------------------------------------------------------------

def test_aux_with_error_names_the_aux_open_at_the_first_error(tmp_path):
    log = tmp_path / "doc.log"
    log.write_text("(./doc.aux\n! Undefined control sequence.\nl.26 \\@LN@col\n"
                   "! LaTeX Error: Missing \\begin{document}.\n")
    assert auxfiles.aux_with_error(log) == [tmp_path / "doc.aux"]
    log.write_text("(./doc.aux (./ch1.aux\n! Undefined control sequence.\n")
    assert auxfiles.aux_with_error(log) == [tmp_path / "ch1.aux"]
    # the .aux files were read without error; the error is in the document
    log.write_text("(./doc.aux (./ch1.aux)) (./ch1.tex\n! Undefined control sequence.\n")
    assert auxfiles.aux_with_error(log) == []
    log.write_text("(./doc.aux)\nno error\n")
    assert auxfiles.aux_with_error(log) == []


def test_documentclass():
    assert auxfiles.documentclass("% \\documentclass{old}\n\\documentclass[a,\n b]{sn-jnl}\n") \
        == "sn-jnl"
    assert auxfiles.documentclass("\\documentclass{article}\n") == "article"
    assert auxfiles.documentclass("no class\n") is None


def test_reset_on_class_change(tmp_path, caplog):
    import logging
    suffixes = (".aux", ".bbl", ".out")
    jobs = ["doc", "doc-draft"]
    tex = tmp_path / "doc.tex"
    tex.write_text("\\documentclass[11pt]{copernicus}\n")
    for name in ("doc.aux", "doc-draft.aux", "doc.bbl", "doc.out", "ch1.aux", "doc.log"):
        (tmp_path / name).write_text("\\@input{ch1.aux}\n" if name == "doc.aux" else "x\n")
    # no record yet: nothing deleted, the class recorded
    assert auxfiles.reset_on_class_change(tmp_path, "doc.tex", jobs, suffixes) == []
    assert (tmp_path / "doc.texmark-class").read_text() == "copernicus\n"
    # same class
    assert auxfiles.reset_on_class_change(tmp_path, "doc.tex", jobs, suffixes) == []
    # another class: the job files and the chapter .aux they read
    tex.write_text("\\documentclass[sn-nature]{sn-jnl}\n")
    with caplog.at_level(logging.INFO, logger="texmark"):
        deleted = auxfiles.reset_on_class_change(tmp_path, "doc.tex", jobs, suffixes)
    assert sorted(deleted) == ["ch1.aux", "doc-draft.aux", "doc.aux", "doc.bbl", "doc.out"]
    assert (tmp_path / "doc.log").exists()
    assert (tmp_path / "doc.texmark-class").read_text() == "sn-jnl\n"
    assert any("changed from copernicus to sn-jnl" in r.getMessage() for r in caplog.records)


def _article(src, template="default", text="Edited."):
    (src / "doc.md").write_text(
        f"---\ntitle: T\njournal:\n  template: {template}\n---\n\n"
        f"# One {{#sec:one}}\n\n{text} See Section \\ref{{sec:one}}.\n")


def _add_lineno_lines(build):
    """What the .aux files of a build under a class that loads lineno look
    like to a class that does not: \\@LN is undefined."""
    for f in build.glob("doc*.aux"):
        first, rest = f.read_text().split("\n", 1)
        lines = "".join(f"\\@LN{{{k}}}{{1}}\n" for k in range(120))
        f.write_text(first + "\n" + lines + rest)


@needs_latex
@pytest.mark.parametrize("switch", [True, False])
def test_aux_of_another_class(tmp_path, monkeypatch, caplog, switch):
    """.aux files whose lines the current class cannot read (lineno's \\@LN,
    after a switch from a class that loads lineno): deleted before the run
    when the document class changed since the last build, or after the run
    that stopped on them otherwise. The build succeeds, references resolved."""
    import logging
    src = tmp_path / "src"
    src.mkdir()
    build = tmp_path / "build"
    _article(src, text="First.")
    monkeypatch.chdir(src)

    def texmark():
        monkeypatch.setattr(sys, "argv", ["texmark", "doc.md", "--pdf", "--progressive",
                                          "-d", str(build), "-o", str(build / "doc.pdf")])
        B.main()

    texmark()
    _add_lineno_lines(build)
    _article(src, "report" if switch else "default")
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="texmark"):
        texmark()
    messages = [r.getMessage() for r in caplog.records]
    assert any("changed from article to report" in m for m in messages) == switch
    assert any("stopped on an error in" in m for m in messages) != switch
    assert not any("build failed" in m for m in messages)
    text = _pdftext(build / "doc.pdf")
    assert "Edited" in text and "??" not in text
    assert all("\\@LN" not in f.read_text() for f in build.glob("doc*.aux"))
