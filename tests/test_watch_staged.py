"""Staged, interruptible --watch builds (texmark.watch, texmark.procs):
interruption and rollback, generations, the part job for chapter edits,
the build-directory lock and clean shutdown.

The watcher runs in-process (texmark.build.watch_project in a thread, with a
short poll interval), except for the signal tests, which run texmark in a
subprocess. Skips when pandoc, latexmk or pdflatex is missing.
"""
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import texmark.build as B
from texmark import procs, watch
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


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def wait_for(cond, timeout=60.0, step=0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(step)
    return False


def processes_in(directory):
    """PIDs of the processes whose working directory is ``directory`` (the
    LaTeX tools run in the build directory)."""
    target = str(Path(directory).resolve())
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if os.readlink(entry / "cwd") == target:
                pids.append(int(entry.name))
        except OSError:
            pass
    return pids


def pdftext(pdf):
    return subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout


def record_publishes(monkeypatch):
    """Record (job, text of the PDF) for each published PDF."""
    published = []
    real = B.publish_pdf

    def recording(src, dst):
        published.append((Path(src).stem, pdftext(src)))
        real(src, dst)

    monkeypatch.setattr(B, "publish_pdf", recording)
    return published


class Watcher:
    """watch_project running in a thread."""

    def __init__(self, argv):
        args = B._build_parser().parse_args([str(a) for a in argv])
        self.plan = B.plan_project(args)
        self.worker = watch.Worker()
        self.stop = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        try:
            B.watch_project(self.plan, interval=0.05, stop=self.stop, worker=self.worker)
        except BaseException as e:  # pragma: no cover - reported by close()
            self.error = e

    def __enter__(self):
        self.thread.start()
        return self

    def idle(self, timeout=120):
        """Wait until the stages of the latest change are done."""
        return wait_for(lambda: self.worker._thread is not None and self.worker.wait(0.05),
                        timeout)

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(60)
        assert not self.thread.is_alive()
        if self.error:
            raise self.error


def edit(path, text):
    """Write ``path`` with a new mtime (the watcher compares mtimes)."""
    before = path.stat().st_mtime_ns if path.exists() else 0
    path.write_text(text)
    if path.stat().st_mtime_ns == before:
        os.utime(path, ns=(before + 1_000_000, before + 1_000_000))


# A book whose chapter 2 can be made slow in the full job (job name "root"):
# when <build>/slow.flag exists, it writes <build>/slow-started.txt and loops
# for 60 s, inside \include{ch2}, i.e. while ch2.aux is open and empty.
SLOW = r"""
```{=latex}
\IfFileExists{slow.flag}{\ifnum\pdfstrcmp{\jobname}{root}=0
\immediate\openout15=slow-started.txt \immediate\write15{x}\immediate\closeout15
\pdfresettimer\loop\ifnum\pdfelapsedtime<3932160 \repeat\fi}{}
```
"""

PNG = REPO_ROOT / "tests" / "fixtures" / "multifile_figures" / "repo-images" / "foo.png"


def chapter(i, extra="", slow=False):
    filler = "\n\n".join(
        f"Filler paragraph {k} of chapter {i} with words to take space on the page."
        for k in range(30))
    return (f"---\ntitle: C{i}\n---\n\n# Chapter {i} {{#sec:c{i}}}\n\n"
            + (SLOW if slow else "")
            + f"MARKER{i} see Chapter \\ref{{sec:c3}} on page \\pageref{{sec:c3}} "
            f"and @knuth, and Chapter \\ref{{sec:c2}}.\n\n![A figure](fig.png){{#fig:f{i} width=30%}}\n\n"
            + extra + filler + "\n")


def make_book(tmp_path, root_extra=""):
    src = tmp_path / "src"
    src.mkdir()
    shutil.copy(PNG, src / "fig.png")
    (src / "refs.bib").write_text(
        "@book{knuth, author={Donald Knuth}, title={The TeXbook}, "
        "year={1984}, publisher={AW}}\n")
    (src / "root.md").write_text(
        "---\ntitle: A Book\njournal:\n  template: book\nbibliography: refs.bib\n"
        "chapters: [ch1.md, ch2.md, ch3.md]\n---\n" + root_extra)
    for i in (1, 2, 3):
        (src / f"ch{i}.md").write_text(chapter(i, slow=(i == 2)))
    return src


def page_of(text, marker):
    """The page number printed on the page containing ``marker`` (a
    chapter's first page: in the footer, the last line)."""
    for page in text.split("\f"):
        if marker in page:
            return page.strip().splitlines()[-1].strip()
    return None


# ---------------------------------------------------------------------------
# process groups (no LaTeX needed)
# ---------------------------------------------------------------------------

def test_cancel_stops_process_group(tmp_path):
    """Cancel stops the command and the processes it started; the next
    command of a cancelled thread is not started."""
    cancel = procs.Cancel()
    result = {}

    def target():
        with procs.cancellable(cancel):
            try:
                procs.run(["sh", "-c", "sleep 30 & sleep 30"], cwd=tmp_path)
            except procs.Interrupted:
                result["interrupted"] = True
            try:
                procs.run(["true"])
            except procs.Interrupted:
                result["second"] = True

    t = threading.Thread(target=target)
    t.start()
    assert wait_for(lambda: len(processes_in(tmp_path)) >= 2, 10)
    t0 = time.monotonic()
    cancel.cancel()
    t.join(10)
    assert time.monotonic() - t0 < 3
    assert result == {"interrupted": True, "second": True}
    assert processes_in(tmp_path) == []


def test_stage_runner_restores_snapshot_on_interrupt(tmp_path):
    """A stopped stage gets its job files back; a finished stage leaves its
    own; no snapshot directory is left."""
    build = tmp_path / "build"
    build.mkdir()
    (build / "doc.aux").write_text("complete")
    (build / "ch1.aux").write_text("complete")
    (build / "doc.tex").write_text("tex")
    snapshot = watch.Snapshot(build, ["doc", "doc-draft"])

    def stopped():
        (build / "doc.aux").write_text("partial")
        (build / "ch1.aux").write_text("")
        (build / "doc-draft.log").write_text("new")
        (build / "doc.tex").write_text("tex2")
        raise procs.Interrupted()

    with pytest.raises(procs.Interrupted):
        watch.run_stages([watch.Stage("x", stopped)], snapshot)
    assert (build / "doc.aux").read_text() == "complete"
    assert (build / "ch1.aux").read_text() == "complete"
    assert not (build / "doc-draft.log").exists()
    assert (build / "doc.tex").read_text() == "tex2"   # not a job file
    assert not (build / watch.SNAPSHOT_DIR).exists()

    def finished():
        (build / "doc.aux").write_text("new")

    watch.run_stages([watch.Stage("y", finished)], snapshot)
    assert (build / "doc.aux").read_text() == "new"
    assert not (build / watch.SNAPSHOT_DIR).exists()


def test_stale_snapshot_restored_at_start(tmp_path, monkeypatch, caplog):
    """A snapshot left by a run that did not finish is restored by the next
    texmark run before it builds."""
    import logging
    monkeypatch.chdir(tmp_path)
    (tmp_path / "doc.md").write_text("---\ntitle: T\n---\n\n# Intro\n")
    build = tmp_path / "build"
    build.mkdir()
    (build / "doc.aux").write_text("complete")
    watch.Snapshot(build, ["doc", "doc-draft"]).take()
    (build / "doc.aux").write_text("partial")
    (build / "doc-draft.aux").write_text("partial")
    (build / (watch.SNAPSHOT_DIR + ".tmp")).mkdir()

    monkeypatch.setattr(sys, "argv", ["texmark", "doc.md", "-d", str(build)])
    with caplog.at_level(logging.INFO, logger="texmark"):
        B.main()
    assert (build / "doc.aux").read_text() == "complete"
    assert not (build / "doc-draft.aux").exists()
    assert not (build / watch.SNAPSHOT_DIR).exists()
    assert not (build / (watch.SNAPSHOT_DIR + ".tmp")).exists()
    assert any("restored the LaTeX files" in r.getMessage() for r in caplog.records)


def test_lock_refuses_build_while_watching(tmp_path, monkeypatch, caplog):
    """A build in a directory locked by a watch session exits with an error;
    one locked by a one-off build waits for it."""
    import logging
    monkeypatch.chdir(tmp_path)
    (tmp_path / "doc.md").write_text("---\ntitle: T\n---\n\n# Intro\n")
    build = tmp_path / "build"
    monkeypatch.setattr(sys, "argv", ["texmark", "doc.md", "-d", str(build)])

    with watch.BuildLock(build, watch=True):
        with pytest.raises(SystemExit) as exc, \
                caplog.at_level(logging.INFO, logger="texmark"):
            B.main()
    assert exc.value.code == 1
    assert any("--watch session" in r.getMessage() for r in caplog.records)
    assert not (build / "doc.tex").exists()

    lock = watch.BuildLock(build).acquire()
    threading.Timer(0.5, lock.release).start()
    caplog.clear()
    t0 = time.monotonic()
    with caplog.at_level(logging.INFO, logger="texmark"):
        B.main()
    assert time.monotonic() - t0 >= 0.4
    assert any("waiting for texmark process" in r.getMessage() for r in caplog.records)
    assert (build / "doc.tex").exists()


# ---------------------------------------------------------------------------
# watch sessions with LaTeX
# ---------------------------------------------------------------------------

@needs_latex
def test_interrupt_figures_stage_restores_aux(tmp_path, monkeypatch):
    """A change during stage 3 stops it (no LaTeX process left from it), puts
    back the .aux files it had emptied (ch2.aux, open while it was stopped),
    and the next draft pass shows every reference."""
    src = make_book(tmp_path)
    build = tmp_path / "build"
    monkeypatch.chdir(src)
    published = record_publishes(monkeypatch)
    with Watcher(["root.md", "--pdf", "--progressive", "-d", build, "-o",
                  build / "out.pdf"]) as w:
        assert w.idle()
        assert published[-1][0] == "root"
        assert "sec:c3" in (build / "ch3.aux").read_text()

        (build / "slow.flag").write_text("")
        edit(src / "root.md", (src / "root.md").read_text() + "\nRoot text.\n")
        assert wait_for(lambda: (build / "slow-started.txt").exists(), 120)
        slow = processes_in(build)
        assert slow
        assert (build / "ch2.aux").read_text() == ""   # open by the stopped job

        published.clear()
        (build / "slow.flag").unlink()
        edit(src / "root.md", (src / "root.md").read_text() + "\nMore root text.\n")
        assert wait_for(lambda: published, 60)
        assert not set(slow) & set(processes_in(build))
        job, text = published[0]
        assert job == "root-draft"
        assert "MARKER2" in text and "??" not in text
        assert "sec:c2" in (build / "ch2.aux").read_text()
        assert w.idle()
    assert processes_in(build) == []
    assert not (build / watch.SNAPSHOT_DIR).exists()


@needs_latex
def test_rapid_changes_publish_in_order(tmp_path, monkeypatch):
    """Changes saved in quick succession: a stage of an older change never
    publishes after a newer one, and the final PDF has the last change."""
    src = make_book(tmp_path)
    build = tmp_path / "build"
    monkeypatch.chdir(src)
    published = record_publishes(monkeypatch)
    with Watcher(["root.md", "--pdf", "--progressive", "-d", build, "-o", build / "out.pdf"]) as w:
        assert w.idle()
        published.clear()
        for n in range(1, 6):
            edit(src / "root.md", (src / "root.md").read_text() + f"\nEDIT{n}\n")
            time.sleep(0.4 + 0.3 * (n % 2))
        assert w.idle()
    seen = [max([n for n in range(1, 6) if f"EDIT{n}" in text] or [0])
            for _job, text in published]
    assert seen == sorted(seen)
    assert seen[-1] == 5
    assert published[-1][0] == "root"
    assert "EDIT5" in pdftext(build / "out.pdf")


@needs_latex
def test_chapter_edit_typesets_that_chapter_first(tmp_path, monkeypatch, caplog):
    """Editing one chapter: stage 1 is the part job with that chapter only,
    numbered as in the full document (pages, references, citations), and
    without the reference list; stages 2 and 3 publish the whole document."""
    import logging
    src = make_book(tmp_path)
    build = tmp_path / "build"
    monkeypatch.chdir(src)
    published = record_publishes(monkeypatch)
    with Watcher(["root.md", "--pdf", "--progressive", "-d", build, "-o", build / "out.pdf"]) as w:
        assert w.idle()
        full = published[-1][1]
        published.clear()
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="texmark"):
            edit(src / "ch2.md", chapter(2, extra="EDITED words.\n\n", slow=True))
            assert wait_for(lambda: len(published) >= 3, 120)
            assert w.idle()

    jobs = [job for job, _ in published]
    assert jobs == ["root-part-draft", "root-draft", "root"]
    part = published[0][1]
    assert "MARKER2" in part and "EDITED" in part
    assert "MARKER1" not in part and "MARKER3" not in part
    assert "??" not in part
    assert "Bibliography" not in part and "Bibliography" in full
    assert page_of(part, "MARKER2") == page_of(full, "MARKER2")
    ref = r"MARKER2 see Chapter 3\s+on\s+page\s+(\d+)"
    assert re.search(ref, part).group(1) == re.search(ref, full).group(1)
    assert "Knuth" in part and "(?)" not in part   # citation from the .bbl
    messages = [r.getMessage() for r in caplog.records]
    assert any("draft PDF of ch2 (1 pass) written" in m for m in messages)


@needs_latex
def test_draft_watch_has_no_figures_stage(tmp_path, monkeypatch):
    """--progressive --draft in watch mode: stages 1 and 2 only."""
    src = make_book(tmp_path)
    build = tmp_path / "build"
    monkeypatch.chdir(src)
    published = record_publishes(monkeypatch)
    with Watcher(["root.md", "--pdf", "--progressive", "--draft", "-d", build,
                  "-o", build / "out.pdf"]) as w:
        assert w.idle()
        published.clear()
        edit(src / "root.md", (src / "root.md").read_text() + "\nNew root text.\n")
        assert wait_for(lambda: published, 60)
        assert w.idle()
    assert {job for job, _ in published} == {"root-draft"}
    assert not (build / "root.log").exists()


@needs_latex
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_signal_stops_watch_cleanly(tmp_path, sig):
    """Ctrl+C (or SIGTERM/SIGHUP) during stage 3: texmark exits, no LaTeX
    process is left, the emptied ch2.aux is restored and the lock released."""
    src = make_book(tmp_path)
    build = tmp_path / "build"
    cmd = [sys.executable, "-m", "texmark.build", "root.md", "--pdf", "--watch",
           "--progressive", "-d", str(build)]
    subprocess.run(cmd[:5] + cmd[6:], cwd=src, check=True,
                   capture_output=True)   # first build, without --watch
    (build / "slow.flag").write_text("")
    proc = subprocess.Popen(cmd, cwd=src, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        edit(src / "root.md", (src / "root.md").read_text() + "\nRoot text.\n")
        assert wait_for(lambda: (build / "slow-started.txt").exists(), 120)
        assert processes_in(build)
        proc.send_signal(sig)
        proc.wait(30)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert processes_in(build) == []
    assert "sec:c2" in (build / "ch2.aux").read_text()
    assert not (build / watch.SNAPSHOT_DIR).exists()
    with watch.BuildLock(build, watch=True):   # free again
        pass
