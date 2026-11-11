"""Running the LaTeX tools (pdflatex, latexmk, bibtex, ...) so that they can
be stopped.

Each command runs in its own process group (a new session), so that stopping
it also stops the processes it starts (latexmk runs pdflatex and bibtex).
Stopping a group sends SIGTERM to all its processes, then SIGKILL to those
still there after a timeout (2 s), and waits until they are gone.

A thread that runs commands on behalf of a watch session does so under a
``Cancel`` object (``with cancellable(cancel): ...``). Another thread calls
``cancel.cancel()`` to stop the command that is running and make the next
one raise ``Interrupted`` instead of starting. Without a ``Cancel`` object,
commands run as before, except that a ``KeyboardInterrupt`` (Ctrl+C, or the
SIGTERM/SIGHUP handlers that ``texmark.build.main`` installs) stops the
running command's group before it propagates: since the command is in
another session, the terminal's SIGINT does not reach it.
"""
import os
import signal
import subprocess
import threading
import time
from contextlib import contextmanager

STOP_TIMEOUT = 2.0


class Interrupted(Exception):
    """The commands of this thread were cancelled."""


class Cancel:
    """Cancellation of the commands run by one thread (see the module doc)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._procs = set()
        self.cancelled = False

    def cancel(self, timeout=STOP_TIMEOUT):
        """Stop the running command, if any, and refuse to start new ones.
        Returns once the stopped processes are gone."""
        with self._lock:
            self.cancelled = True
            procs = list(self._procs)
        for proc in procs:
            stop_group(proc, timeout)


_local = threading.local()


@contextmanager
def cancellable(cancel):
    """Run the commands of the current thread under ``cancel``."""
    previous = getattr(_local, 'cancel', None)
    _local.cancel = cancel
    try:
        yield cancel
    finally:
        _local.cancel = previous


def check():
    """Raise ``Interrupted`` when the current thread's commands were cancelled."""
    cancel = getattr(_local, 'cancel', None)
    if cancel is not None and cancel.cancelled:
        raise Interrupted()


def _group_alive(pgid):
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_gone(proc, timeout):
    """Wait until the process group of ``proc`` has no process left. Returns
    False on timeout. ``proc.poll()`` reaps the group leader when this thread
    can (otherwise the thread blocked in ``proc.wait()`` does)."""
    deadline = time.monotonic() + timeout
    while True:
        proc.poll()
        if not _group_alive(proc.pid):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.02)


def stop_group(proc, timeout=STOP_TIMEOUT):
    """SIGTERM to the process group of ``proc`` (a group leader), SIGKILL
    after ``timeout`` seconds, and wait until it is gone."""
    for sig, wait in ((signal.SIGTERM, timeout), (signal.SIGKILL, 5.0)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        if _wait_gone(proc, wait):
            return


def run(cmd, cwd=None, check=False, shell=False, **kwargs):
    """``subprocess.run`` for a command in its own process group, stopped
    by a ``Cancel`` of the current thread or by a KeyboardInterrupt.
    Returns a ``subprocess.CompletedProcess`` (without captured output)."""
    cancel = getattr(_local, 'cancel', None)

    def start():
        return subprocess.Popen(cmd, cwd=cwd, shell=shell,
                                start_new_session=True, **kwargs)

    if cancel is None:
        proc = start()
    else:
        with cancel._lock:
            if cancel.cancelled:
                raise Interrupted()
            proc = start()
            cancel._procs.add(proc)
    try:
        returncode = proc.wait()
    except BaseException:
        stop_group(proc)
        proc.wait()
        raise
    finally:
        if cancel is not None:
            with cancel._lock:
                cancel._procs.discard(proc)
    if cancel is not None and cancel.cancelled:
        raise Interrupted()
    if check and returncode:
        raise subprocess.CalledProcessError(returncode, cmd)
    return subprocess.CompletedProcess(cmd, returncode)
