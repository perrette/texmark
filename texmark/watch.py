"""Build stages, the build-directory lock, and the watch loop.

A PDF build is a list of stages (``Stage``), each of which runs LaTeX tools
and may publish a PDF: one stage for a plain build, up to three for a
progressive one (see ``texmark.build.compile_stages``). ``run_stages`` runs
them in order. Before each stage it saves the files the LaTeX jobs write
(``Snapshot``); when a stage is stopped half-way, it puts them back, so the
next run starts from complete .aux/.bbl/... files instead of the partial ones
of the stopped run.

In watch mode, the stages of a change run in a background thread
(``Worker``) while the watch loop keeps polling the sources. A new change
stops them (``texmark.procs``), and their files are restored before the
stages of the new change start. Each change gets a number (generation); a
stage publishes its PDF only while its change is the latest one.

``BuildLock`` keeps two texmark processes from writing the same build
directory: a one-off build holds it for the build, a watch session for the
whole session. A process that finds the lock taken waits for it when the
holder is a one-off build, and exits with an error when the holder is a
watch session (which would not release it until stopped).
"""
import fcntl
import json
import os
import shutil
import signal
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from texmark import procs
from texmark.logs import logger

LOCK_FILE = '.texmark.lock'
SNAPSHOT_DIR = '.texmark-snapshot'
# Files the snapshot leaves out: the .tex files (inputs, written by the
# markdown conversion), the precompiled preamble (its record,
# <stem>-preamble.json, says when it must be rebuilt) and the job PDFs, which
# the engine rewrites on every pass and no pass reads (latexmk only checks
# that the PDF exists; after a stopped stage it reruns anyway, since its
# restored .fdb_latexmk predates the stopped run).
_NOT_SAVED = ('.tex', '.fmt', '.pdf')


# ---------------------------------------------------------------------------
# Build-directory lock
# ---------------------------------------------------------------------------

class BuildDirBusy(Exception):
    """The build directory is used by a texmark watch session."""


class BuildLock:
    """``fcntl.flock`` on ``<build_dir>/.texmark.lock`` (see the module doc).

    The holder writes ``<pid> watch|build`` into the file, so that another
    process can tell what it is waiting for.
    """

    def __init__(self, build_dir, watch=False):
        self.path = Path(build_dir) / LOCK_FILE
        self.watch = watch
        self._fd = None

    def _holder(self):
        try:
            return self.path.read_text().split()
        except OSError:
            return []

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                holder = self._holder()
                if len(holder) == 2 and holder[1] == 'watch':
                    raise BuildDirBusy(
                        f"texmark: the build directory {self.path.parent} is used by "
                        f"a texmark --watch session (pid {holder[0]}); stop it or "
                        "build in another directory (-d).")
                who = f"texmark process {holder[0]}" if holder else "another texmark process"
                logger.info(f"texmark: waiting for {who} to finish building in "
                            f"{self.path.parent}")
                fcntl.flock(fd, fcntl.LOCK_EX)
            os.ftruncate(fd, 0)
            os.write(fd, f"{os.getpid()} {'watch' if self.watch else 'build'}\n".encode())
        except BaseException:
            os.close(fd)
            raise
        self._fd = fd
        return self

    def release(self):
        if self._fd is None:
            return
        try:
            os.ftruncate(self._fd, 0)
        finally:
            os.close(self._fd)  # also releases the lock
            self._fd = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *exc):
        self.release()


# ---------------------------------------------------------------------------
# Snapshot of the job files
# ---------------------------------------------------------------------------

def _job_files(build_dir, jobs, keep=()):
    """Files in ``build_dir`` written by the LaTeX jobs ``jobs`` (``<job>.*``)
    and every .aux file (the chapter .aux files that \\include writes and
    xr-hyper reads), except the .tex, .fmt and .pdf files; the file names in
    ``keep`` are included anyway."""
    try:
        entries = list(Path(build_dir).iterdir())
    except FileNotFoundError:
        return []
    files = []
    for f in entries:
        if f.name in keep and f.is_file():
            files.append(f)
            continue
        if f.suffix in _NOT_SAVED or f.name.startswith('.') or not f.is_file():
            continue
        if f.suffix == '.aux' or any(f.name.startswith(job + '.') for job in jobs):
            files.append(f)
    return files


class Snapshot:
    """Copy of the job files in ``<build_dir>/.texmark-snapshot/``.

    ``take`` copies them into a temporary directory renamed into place when
    complete, so an existing snapshot directory is always a complete one.
    ``restore`` deletes the job files that were not there when the snapshot
    was taken, copies the saved ones back (each through a temporary file
    renamed over the original), and removes the snapshot. ``drop`` removes it.

    ``keep``: file names saved although they are PDFs, i.e. the output PDF
    when it is the full job's own (the file the viewer shows).
    """

    _MANIFEST = '.jobs.json'

    def __init__(self, build_dir, jobs, keep=()):
        self.build_dir = Path(build_dir)
        self.jobs = list(jobs)
        self.keep = list(keep)
        self.dir = self.build_dir / SNAPSHOT_DIR

    def take(self):
        tmp = self.dir.with_name(SNAPSHOT_DIR + '.tmp')
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        for f in _job_files(self.build_dir, self.jobs, self.keep):
            shutil.copy2(f, tmp / f.name)
        (tmp / self._MANIFEST).write_text(json.dumps({'jobs': self.jobs, 'keep': self.keep}))
        shutil.rmtree(self.dir, ignore_errors=True)
        tmp.rename(self.dir)

    def drop(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def restore(self):
        return restore_snapshot(self.build_dir)


def restore_snapshot(build_dir):
    """Restore the snapshot in ``build_dir``, if there is one (see Snapshot).
    Returns True when one was restored. Called at the start of each texmark
    run, for a snapshot left by a run that did not finish (crash, kill -9)."""
    build_dir = Path(build_dir)
    snap = build_dir / SNAPSHOT_DIR
    shutil.rmtree(build_dir / (SNAPSHOT_DIR + '.tmp'), ignore_errors=True)
    try:
        manifest = json.loads((snap / Snapshot._MANIFEST).read_text())
        jobs, keep = manifest['jobs'], manifest['keep']
    except (OSError, ValueError, KeyError, TypeError):
        shutil.rmtree(snap, ignore_errors=True)
        return False
    saved = {f.name for f in snap.iterdir() if f.name != Snapshot._MANIFEST}
    for f in _job_files(build_dir, jobs, keep):
        if f.name not in saved:
            f.unlink(missing_ok=True)
    for name in saved:
        tmp = build_dir / f'.{name}.restore.tmp'
        shutil.copy2(snap / name, tmp)
        os.replace(tmp, build_dir / name)
    shutil.rmtree(snap, ignore_errors=True)
    return True


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

@dataclass
class Stage:
    """``run()`` does the work of the stage and returns a function that
    publishes its PDF, or None when there is nothing to publish (it logs
    why). ``name`` is used in the message printed after publishing."""
    name: str
    run: Callable[[], Optional[Callable[[], None]]]


def _publish_now(publish):
    publish()
    return True


def run_stages(stages, snapshot=None, t0=None, output=None, publish=_publish_now):
    """Run ``stages`` in order, saving the job files before each one and
    restoring them when the stage is stopped (``procs.Interrupted``,
    KeyboardInterrupt). ``publish(fn)`` calls ``fn`` and returns True, or
    returns False when the PDF must not be published (a newer change).
    After each published PDF, prints the stage name and the time since ``t0``.
    """
    t0 = time.monotonic() if t0 is None else t0
    for stage in stages:
        procs.check()
        if snapshot is not None:
            snapshot.take()
        try:
            publish_fn = stage.run()
        except (procs.Interrupted, KeyboardInterrupt, SystemExit):
            if snapshot is not None:
                snapshot.restore()
            raise
        except BaseException:
            if snapshot is not None:
                snapshot.drop()
            raise
        if snapshot is not None:
            snapshot.drop()
        if publish_fn is not None and publish(publish_fn):
            logger.info(f"texmark: {stage.name} written: {output} "
                        f"({time.monotonic() - t0:.1f} s)")


class Worker:
    """Runs the stages of the latest change in a background thread.

    ``start`` stops the stages of the previous change (``cancel``) and starts
    the new ones. ``cancel`` stops the running command, waits until the thread
    has restored the job files and ended, and from then on refuses the PDFs of
    the stopped stages (the generation number has changed).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._generation = 0
        self._thread = None
        self._cancel = None

    def start(self, stages, snapshot=None, t0=None, output=None):
        self.cancel()
        with self._lock:
            self._generation += 1
            generation = self._generation
        cancel = procs.Cancel()

        def publish(fn):
            with self._lock:
                if generation != self._generation:
                    return False
                fn()
                return True

        def target():
            with procs.cancellable(cancel):
                try:
                    run_stages(stages, snapshot, t0, output, publish)
                except procs.Interrupted:
                    logger.info("texmark: stopped the running build (newer change "
                                "or shutdown); its .aux files were restored.")
                except Exception as e:
                    logger.error(f"texmark: build failed: {e}")
                else:
                    logger.info("texmark: build OK; watching for next change.")

        self._cancel = cancel
        self._thread = threading.Thread(target=target, name='texmark-stages', daemon=True)
        self._thread.start()

    def cancel(self):
        with self._lock:
            self._generation += 1
        if self._cancel is not None:
            self._cancel.cancel()
        if self._thread is not None:
            self._thread.join()
        self._thread = self._cancel = None

    def wait(self, timeout=None):
        """Wait until the current stages are done (for tests). Returns False
        on timeout."""
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            return not thread.is_alive()
        return True


# ---------------------------------------------------------------------------
# Watch loop and signals
# ---------------------------------------------------------------------------

def _raise_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt()


def stop_on_signals():
    """Make SIGTERM and SIGHUP stop texmark like Ctrl+C (KeyboardInterrupt),
    so that running LaTeX processes are stopped and the lock released. Only
    possible in the main thread; does nothing elsewhere."""
    if threading.current_thread() is not threading.main_thread():
        return
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, _raise_keyboard_interrupt)


@contextmanager
def signals_ignored():
    """Ignore SIGINT/SIGTERM/SIGHUP during cleanup, so that a second Ctrl+C
    does not leave a stage half-stopped (main thread only)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    sigs = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous = {sig: signal.signal(sig, signal.SIG_IGN) for sig in sigs}
    try:
        yield
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def _mtimes(paths):
    out = {}
    for p in paths:
        try:
            out[p] = p.stat().st_mtime_ns
        except FileNotFoundError:
            pass
    return out


def watch_loop(do_build, paths, interval=0.5, stop=None):
    """Call ``do_build(changed)`` whenever some of ``paths`` change mtime,
    with the set of changed paths. Loops until Ctrl+C (or SIGTERM/SIGHUP, see
    ``stop_on_signals``), or until the ``threading.Event`` ``stop`` is set.

    Callers are expected to have run an initial build already, so mtimes are
    taken here and do_build is only called on later changes.
    """
    paths = [Path(p) for p in paths if p]
    last = _mtimes(paths)
    logger.info(f"texmark: watching {len(paths)} path(s); Ctrl-C to stop.")
    try:
        while True:
            if stop is None:
                time.sleep(interval)
            elif stop.wait(interval):
                break
            now = _mtimes(paths)
            changed = {p for p in now if last.get(p) != now[p]}
            last.update(now)
            if changed:
                try:
                    do_build(changed)
                except Exception as e:
                    logger.error(f"texmark: build failed: {e}")
    except KeyboardInterrupt:
        pass
    logger.info("texmark: stopped watching.")
