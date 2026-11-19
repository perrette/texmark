"""Checking the .aux files in the build directory before a LaTeX run.

A LaTeX run that is stopped half-way (or a copy that was cut short) can
leave an .aux file that ends in the middle of a line. The next run reads it
with ``\\input`` (or xr-hyper with ``\\read``) and fails with "File ended
while scanning use of ..." or "File ended within \\read", and keeps failing
until the file is removed. So before each engine pass and latexmk run,
``check_aux_files`` looks at every .aux file in the build directory:

- braces are balanced (not counting ``\\{``, ``\\}`` and what follows an
  unescaped ``%`` on a line) and the file ends with a newline;
- a chapter .aux (one written by ``\\include``: it contains
  ``\\@setckpt{<name>}{``, or another .aux reads it with ``\\@input``) ends
  with the ``}`` that closes ``\\@setckpt{<name>}{...}``, which LaTeX writes
  when the chapter is finished;
- a main .aux ends with ``\\gdef \\@abspage@last{<n>}`` when it has that line
  (LaTeX since 2020-10 writes it at the end of the document); without it,
  the two rules of the first item suffice (older kernels, or a run that
  ended with an error, whose .aux is complete up to the error).

A file that fails is restored from the stage snapshot (texmark.watch) when
the snapshot has a copy that passes, and deleted otherwise, with one info
line. ``runaway_aux`` is the safety net for what these rules miss: it finds,
in the log of a failed run, the .aux file being read when such an error
occurred, so that the caller can delete it and run once more.

A complete .aux can also stop LaTeX: one written under another document
class or package set calls macros the current preamble does not define (the
\\@LN lines of lineno after a switch from the copernicus template), and the
run stops before it writes a new one. ``reset_on_class_change`` records the
document class of each .tex in ``<stem>.texmark-class`` and, when it
changes, deletes the .aux/.bbl/... of the document's jobs before the run.
``aux_with_error`` is the safety net for other cases (a package removed, a
build directory without a record): the .aux being read at the first error
of a failed run, which the caller deletes before running once more.
"""
import re
import shutil
from pathlib import Path

from texmark.logs import logger

SNAPSHOT_DIR = '.texmark-snapshot'   # texmark.watch.SNAPSHOT_DIR
_ABSPAGE = re.compile(r'\\gdef \\@abspage@last\{\d+\}\n\Z')
_INPUT = re.compile(r'\\@input\{([^}]*\.aux)\}')
_RUNAWAY = ('File ended while scanning use of', 'File ended within \\read')


def _depths(text):
    """Brace depth after each character position that closes a group, as a
    list of (position, depth after it), and the final depth."""
    depth, closes = 0, []
    for line_start, line in _lines(text):
        i = 0
        while i < len(line):
            c = line[i]
            if c == '\\':
                i += 2
                continue
            if c == '%':
                break
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth < 0:
                    return closes, depth
                closes.append((line_start + i, depth))
            i += 1
    return closes, depth


def _lines(text):
    pos = 0
    for line in text.splitlines(keepends=True):
        yield pos, line
        pos += len(line)


def aux_problem(text, chapter=False):
    """Why the .aux text ``text`` is incomplete, or None when it is fine."""
    if not text:
        return 'empty'
    if not text.endswith('\n'):
        return 'ends in the middle of a line'
    closes, depth = _depths(text)
    if depth != 0:
        return 'unbalanced braces'
    start = text.find('\\@setckpt{')
    if chapter or start >= 0:
        if start < 0:
            return 'no \\@setckpt (chapter not finished)'
        # \@setckpt{<name>}{...}: the content group must close at the end.
        level0 = [pos for pos, d in closes if d == 0 and pos > start]
        if len(level0) < 2 or text[level0[1] + 1:].strip():
            return 'does not end with the closing of \\@setckpt'
        return None
    if '\\@abspage@last' in text and not _ABSPAGE.search(text):
        return 'does not end with \\@abspage@last'
    return None


def _chapters(files):
    """Names of the .aux files that some .aux reads with \\@input."""
    names = set()
    for f, text in files.items():
        names.update(Path(n).name for n in _INPUT.findall(text))
    return names


def _read(path):
    try:
        return path.read_text(errors='replace')
    except OSError:
        return None


def check_aux_files(build_dir):
    """Restore or delete the incomplete .aux files in ``build_dir`` (see the
    module doc). Returns the names of the files that were incomplete."""
    build_dir = Path(build_dir)
    files = {}
    for f in build_dir.glob('*.aux'):
        text = _read(f)
        if text is not None:
            files[f] = text
    chapters = _chapters(files)
    bad = []
    for f, text in files.items():
        problem = aux_problem(text, f.name in chapters)
        if problem is None:
            continue
        bad.append(f.name)
        saved = build_dir / SNAPSHOT_DIR / f.name
        saved_text = _read(saved)
        if saved_text is not None and aux_problem(saved_text, f.name in chapters) is None:
            tmp = build_dir / f'.{f.name}.restore.tmp'
            shutil.copy2(saved, tmp)
            tmp.replace(f)
            logger.info(f"texmark: {f} was incomplete ({problem}); restored it "
                        "from the snapshot")
        else:
            f.unlink(missing_ok=True)
            logger.info(f"texmark: {f} was incomplete ({problem}); deleted it")
    return bad


def runaway_aux(log_file):
    """The .aux files that the failed run of ``log_file`` was reading when it
    stopped with a runaway-argument error ("File ended while scanning use
    of ...", "File ended within \\read"): the last .aux opened before the
    error in the log, or, when the log names none (xr-hyper reads the peer
    .aux files with \\read), every .aux that check_aux_files rejects."""
    log_file = Path(log_file)
    log = _read(log_file)
    if log is None:
        return []
    hit = min((i for i in (log.find(m) for m in _RUNAWAY) if i >= 0), default=-1)
    if hit < 0:
        return []
    opened = list(re.finditer(r'\((?:\./)?([^()\s]+\.aux)', log[:hit]))
    if opened:
        # Still open at the error: its closing parenthesis not yet logged.
        last = opened[-1]
        after = log[last.end():hit]
        if after.count('(') >= after.count(')'):
            return [log_file.parent / Path(last.group(1)).name]
        return []
    files = {f: _read(f) or '' for f in log_file.parent.glob('*.aux')}
    chapters = _chapters(files)
    return [f for f, text in files.items() if aux_problem(text, f.name in chapters)]


def aux_with_error(log_file):
    """The .aux file that the failed run of ``log_file`` was reading when
    LaTeX reported its first error (``! ...``), as a list of one path, or
    an empty list when the first error came from elsewhere.

    An .aux written under another document class or package set can call
    macros that the current preamble does not define (lineno's ``\\@LN``
    after a switch away from a class that loads lineno): every run then
    stops in it, before it can write a new one."""
    log_file = Path(log_file)
    log = _read(log_file)
    if log is None:
        return []
    error = re.search(r'^! ', log, re.M)
    if error is None:
        return []
    hit = error.start()
    opened = list(re.finditer(r'\((?:\./)?([^()\s]+\.aux)', log[:hit]))
    if not opened:
        return []
    last = opened[-1]
    after = log[last.end():hit]
    if after.count('(') >= after.count(')'):
        return [log_file.parent / Path(last.group(1)).name]
    return []


# ---------------------------------------------------------------------------
# Document class of the files in the build directory
# ---------------------------------------------------------------------------

CLASS_RECORD = '.texmark-class'   # <stem>.texmark-class
_DOCUMENTCLASS = re.compile(r'^[ \t]*\\documentclass[ \t]*(?:\[[^\]]*\])?\s*\{([^}]*)\}', re.M)


def documentclass(tex_text):
    """The class name of the ``\\documentclass`` line of ``tex_text``, or
    None."""
    m = _DOCUMENTCLASS.search(tex_text)
    return m.group(1).strip() if m else None


def reset_on_class_change(build_dir, tex_name, jobs, suffixes):
    """Delete the files of the jobs ``jobs`` (``<job><suffix>`` for each of
    ``suffixes``) and the chapter .aux files they read, when the document
    class of ``<build_dir>/<tex_name>`` differs from the one recorded in
    ``<stem>.texmark-class`` by the previous call. These files were written
    under the other class and can make LaTeX stop with errors before it
    writes new ones. Records the current class. Without a record (first
    build, or a build directory of an older texmark), nothing is deleted:
    ``aux_with_error`` covers that case after the run. Returns the names of
    the deleted files."""
    build_dir = Path(build_dir)
    text = _read(build_dir / tex_name)
    cls = documentclass(text) if text is not None else None
    if cls is None:
        return []
    record = build_dir / (Path(tex_name).stem + CLASS_RECORD)
    old = _read(record)
    deleted = []
    if old is not None and old.strip() != cls:
        files = [build_dir / f'{job}{suffix}' for job in jobs for suffix in suffixes]
        for f in [f for f in files if f.suffix == '.aux']:
            for name in _INPUT.findall(_read(f) or ''):
                files.append(build_dir / Path(name).name)
        for f in dict.fromkeys(files):
            if f.exists():
                f.unlink()
                deleted.append(f.name)
        logger.info(f"texmark: the document class changed from {old.strip()} to {cls}; "
                    f"deleted the files of the previous build: {', '.join(deleted) or 'none'}")
    if old is None or old.strip() != cls:
        record.write_text(cls + '\n')
    return deleted
