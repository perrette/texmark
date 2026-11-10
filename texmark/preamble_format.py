"""Precompiled preamble for pdflatex builds (mylatexformat).

Every texmark template ends the static part of its preamble (document
class, packages, title block, user preamble) with the marker line
``\\csname endofdump\\endcsname`` (``PREAMBLE_END`` below, rendered by
build_tex). That part is dumped into a format file once:

    pdflatex -ini -interaction=batchmode -recorder -jobname=<stem>-preamble \\
        "&pdflatex" mylatexformat.ltx <stem>.tex

and each engine pass then starts from it (``pdflatex -fmt=<stem>-preamble``):
mylatexformat skips the source up to the marker line and reads on from
there. What follows the marker is read on every pass: xr-hyper's
``\\externaldocument`` (it reads the peers' .aux), ``\\includeonly``, and
the switch that turns the ``<stem>-draft`` job into a draft (TeX code given
on the command line is skipped together with the preamble, so the draft job
cannot get its option from there).

Without a format, the marker line is a no-op: ``\\csname`` defines the
undefined ``\\endofdump`` as ``\\relax``.

The format is rebuilt when its key changes. The key is a hash of the
preamble text up to the marker, the engine and the first line of its
``--version``, the base format (path and mtime of pdflatex.fmt), and the
files the format build read (from its -recorder .fls): the content of the
files given by relative path (the template resources in the build
directory, files the user preamble inputs), size and mtime of the others
(the TeX distribution). The key and the file list are stored next to the
format in ``<stem>-preamble.json``. Files loaded into the format do not
appear in the .fls of the runs that use it, so latexmk does not see their
changes; a rebuilt format does change the .fmt, which latexmk tracks.

Fallback: the document is compiled the usual way when the engine is not
pdflatex, the backend is not latexmk or raw, the .tex has no marker line
(custom template) or mylatexformat.ltx is not installed (a debug message),
when the format build fails, or when a run with the format fails because
of the format (see ``run_failed``; an info message, and the run is
repeated without the format). The last two are recorded in the .json under
the same key, so later builds do not try again until the preamble changes.
"""
import functools
import hashlib
import json
import subprocess
from pathlib import Path

from texmark.logs import logger

PREAMBLE_END = r'\csname endofdump\endcsname'
SUPPORTED_ENGINES = ('pdflatex',)
SUPPORTED_BACKENDS = ('latexmk', 'raw')
_KEY_VERSION = 'texmark-preamble-format 1'
# Written to the job log by the format's \everyjob code once the preamble
# has been skipped.
_START_MESSAGE = '(mylatexformat)Info: start reading document'


def format_name(tex_name):
    return Path(tex_name).stem + '-preamble'


def draft_switch(draft_jobname):
    """TeX line, placed after the marker, that sets graphicx's draft option
    in the draft job. Guarded so that it does nothing under engines without
    \\pdfstrcmp or when graphicx is not loaded."""
    return (r'\ifdefined\pdfstrcmp\ifcsname KV@Gin@draft\endcsname'
            r'\ifnum\pdfstrcmp{\jobname}{' + draft_jobname + r'}=0 '
            r'\setkeys{Gin}{draft}\fi\fi\fi')


def _output(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except OSError:
        return ''
    return result.stdout.strip() if result.returncode == 0 else ''


@functools.lru_cache(maxsize=None)
def _kpsewhich(*args):
    return _output(['kpsewhich', *args])


def mylatexformat_path():
    return _kpsewhich('mylatexformat.ltx')


@functools.lru_cache(maxsize=None)
def _engine_version(engine):
    return _output([engine, '--version']).split('\n')[0]


def _base_format(engine):
    path = _kpsewhich('-engine=pdftex', f'{engine}.fmt')
    try:
        return f'{path} {Path(path).stat().st_mtime_ns}'
    except OSError:
        return path


def preamble_text(tex_path):
    """The .tex up to and including the marker line, or None."""
    try:
        text = Path(tex_path).read_text(errors='replace')
    except FileNotFoundError:
        return None
    end = text.find('\n' + PREAMBLE_END)
    if end < 0:
        return None
    return text[:end + 1 + len(PREAMBLE_END)]


def _file_entry(build_dir, name):
    path = Path(name) if Path(name).is_absolute() else build_dir / name
    try:
        if Path(name).is_absolute():
            st = path.stat()
            return f'{name} {st.st_size} {st.st_mtime_ns}'
        return f'{name} {hashlib.sha256(path.read_bytes()).hexdigest()}'
    except OSError:
        return f'{name} missing'


def _key(build_dir, preamble, engine, files):
    h = hashlib.sha256()
    for part in [_KEY_VERSION, engine, _engine_version(engine),
                 _base_format(engine), preamble,
                 *(_file_entry(build_dir, f) for f in files)]:
        h.update(part.encode('utf-8', 'surrogateescape'))
        h.update(b'\0')
    return h.hexdigest()


def _recorded_inputs(fls, tex_name):
    """Files read by the format build: INPUT entries of its .fls, minus the
    files it wrote and the .tex itself (its preamble is part of the key)."""
    inputs, outputs = [], set()
    try:
        lines = Path(fls).read_text(errors='replace').splitlines()
    except FileNotFoundError:
        return []
    for line in lines:
        kind, _, name = line.partition(' ')
        if kind == 'INPUT':
            inputs.append(name)
        elif kind == 'OUTPUT':
            outputs.add(name)
    skip = outputs | {tex_name, f'./{tex_name}'}
    return sorted({f for f in inputs if f not in skip})


def _state_file(build_dir, tex_name):
    return Path(build_dir) / f'{format_name(tex_name)}.json'


def _load_state(build_dir, tex_name):
    try:
        return json.loads(_state_file(build_dir, tex_name).read_text())
    except (OSError, ValueError):
        return {}


def _save_state(build_dir, tex_name, **state):
    _state_file(build_dir, tex_name).write_text(json.dumps(state, indent=1) + '\n')


def prepare(build_dir, tex_name, engine, backend):
    """Make sure an up-to-date format exists for ``<build_dir>/<tex_name>``.

    Returns the format name to pass to ``-fmt``, or None to compile without.
    """
    build_dir = Path(build_dir)
    if engine not in SUPPORTED_ENGINES or backend not in SUPPORTED_BACKENDS:
        return None
    preamble = preamble_text(build_dir / tex_name)
    if preamble is None:
        logger.debug(f"texmark: no preamble marker in {tex_name}; "
                     "compiling without a precompiled preamble")
        return None
    if not mylatexformat_path():
        logger.debug("texmark: mylatexformat.ltx not found; "
                     "compiling without a precompiled preamble")
        return None

    name = format_name(tex_name)
    fmt = build_dir / f'{name}.fmt'
    state = _load_state(build_dir, tex_name)
    if state.get('key') == _key(build_dir, preamble, engine, state.get('files', [])):
        if state.get('status') == 'ok' and fmt.exists():
            return name
        if state.get('status') in ('build-failed', 'run-failed'):
            return None

    cmd = [engine, '-ini', '-interaction=batchmode', '-recorder',
           f'-jobname={name}', f'&{engine}', 'mylatexformat.ltx', tex_name]
    logger.info(' '.join(cmd))
    try:
        result = subprocess.run(cmd, cwd=build_dir, check=False,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ok = result.returncode == 0
    except OSError:
        ok = False
    files = _recorded_inputs(build_dir / f'{name}.fls', tex_name)
    key = _key(build_dir, preamble, engine, files)
    if ok and fmt.exists():
        _save_state(build_dir, tex_name, key=key, files=files, status='ok')
        return name
    fmt.unlink(missing_ok=True)
    _save_state(build_dir, tex_name, key=key, files=files, status='build-failed')
    logger.info(f"texmark: building the precompiled preamble failed (see "
                f"{build_dir / (name + '.log')}); compiling without it")
    return None


def _mtime(path):
    try:
        return Path(path).stat().st_mtime_ns
    except OSError:
        return None


def _latexmk_engine_run(fdb):
    """Time of latexmk's last engine run, from its .fdb_latexmk."""
    try:
        for line in Path(fdb).read_text(errors='replace').splitlines():
            if line.startswith('["pdflatex"]'):
                return line.split()[1]
    except (OSError, IndexError):
        pass
    return None


def run_state(build_dir, jobname):
    """The job's .log mtime and latexmk's last engine run time, taken before
    a run and passed to ``run_failed`` after it."""
    build_dir = Path(build_dir)
    return (_mtime(build_dir / f'{jobname}.log'),
            _latexmk_engine_run(build_dir / f'{jobname}.fdb_latexmk'))


def run_failed(build_dir, jobname, before, latexmk=False):
    """Whether a run with the format failed because of the format.

    ``before`` is ``run_state`` taken before the run; ``latexmk`` tells
    whether the run was latexmk's (which may not run the engine at all) or
    engine passes. An engine that cannot load the format ("Fatal format
    file error") writes no log, so a log that was not rewritten although the
    engine ran (latexmk records each engine run in its .fdb_latexmk) is a
    failure. A rewritten log is a failure when it lacks mylatexformat's
    start message, i.e. the preamble scan did not reach the marker line.
    """
    log_before, engine_run_before = before
    log_now, engine_run_now = run_state(build_dir, jobname)
    if log_now is None:
        return True
    if log_now == log_before:
        return not latexmk or engine_run_now != engine_run_before
    log = (Path(build_dir) / f'{jobname}.log').read_text(errors='replace')
    return 'Fatal format file error' in log or _START_MESSAGE not in log


def disable(build_dir, tex_name):
    """Record that the current format does not work for this document."""
    state = _load_state(build_dir, tex_name)
    state['status'] = 'run-failed'
    _save_state(build_dir, tex_name, **state)
    logger.info(f"texmark: the run with the precompiled preamble failed; "
                f"compiling {tex_name} without it")
