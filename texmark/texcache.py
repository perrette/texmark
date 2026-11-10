"""On-disk cache of the .tex files generated for embedded documents.

Each texmark run is a new process, so the in-memory ``parse_markdown`` cache
does not help across runs. This cache lets ``build_project`` skip the
``build_tex`` call of an embedded document (chapter) whose inputs have not
changed since the last run, and keep the .tex it wrote then. The root and
companion documents are always rebuilt: the root is small, and a companion's
returned metadata feeds compile_pdf.

One JSON entry per embedded document, ``<build_dir>/.texmark-cache/<stem>.json``:

``key``
    sha256 over everything known before the build that can change the output:
    the markdown text and its resolved path; every ``build_tex`` argument
    (build dir, journal template, copy_figures, figure_folders, project root,
    peer stems for texmark-crossref, engine, rewrite_unicode, ...); the
    current directory (the filter context stores absolute paths); the
    contents of the preamble and custom template files named in the YAML or
    on the command line; and ``_environment()``: texmark's own files (the .py
    modules and templates), the pandoc binary (path, size, mtime) and the
    panflute version. An embedded document only receives the root's settings
    through these arguments (it reads its own YAML), so they cover inherited
    metadata too.
``deps``
    recorded after the build: size and mtime of every local figure the
    document references (or null if it was missing). In --copy-figures mode
    the bundled names and contents come from these files.
``outputs``
    files the build left in the build dir, which must still be there: the
    .tex (sha256, so a .tex modified by anything else is rebuilt) and, by
    size, the bundled and downloaded figures.

Cross-document references need no extra handling: texmark-crossref only uses
the peer stems (part of the key), not the peers' contents. Labels are
resolved by LaTeX (xr-hyper, .aux files), not by texmark.

The side effects of a skipped build are: the figure copies and downloads
(checked through ``outputs``), the figure manifest (which only accumulates in
a multi-file build, so it already lists the document's figures), and log
warnings (e.g. a missing figure), which are not repeated.

Caching is off for a document that uses user filters or a filters module
(arbitrary code and side effects), or pandoc_args that read other files
(``_FILE_ARGS``). ``--no-cache`` turns it off for the run. A missing,
unreadable or corrupt entry is a cache miss.

The same directory caches the embed scan of ``resolve_project``
(``<stem>.embeds.json``: the files a markdown embeds), which otherwise runs
the pandoc reader on every chapter.
"""
import hashlib
import json
import os
import shutil
from functools import cache
from pathlib import Path

import panflute as pf
import pypandoc

import texmark
from texmark.filters.download_images import safe_filename_from_url
from texmark.filters.images import resolve_image_paths
from texmark.logs import logger
from texmark.project import load_markdown, parse_markdown, _scan_ast_for_embeds

CACHE_DIR = '.texmark-cache'
_FORMAT = 1
_FILE_ARGS = ('--filter', '-F', '--lua-filter', '-L', '--defaults', '-d',
              '--metadata-file', '--citeproc', '-C', '--csl', '--citation-abbreviations',
              '--include-in-header', '-H', '--include-before-body', '-B',
              '--include-after-body', '-A', '--syntax-definition', '--abbreviations')


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@cache
def _environment() -> str:
    """Fingerprint of texmark's files, pandoc and panflute (once per run, ~10 ms)."""
    h = hashlib.sha256(f'{_FORMAT} {pf.__version__}'.encode())
    pkg = Path(texmark.__file__).resolve().parent
    for p in sorted(pkg.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            h.update(str(p.relative_to(pkg)).encode() + b'\0' + p.read_bytes())
    pandoc = shutil.which(pypandoc.get_pandoc_path()) or ''
    st = os.stat(pandoc) if pandoc else None
    h.update(f'{pandoc} {st and st.st_size} {st and st.st_mtime_ns}'.encode())
    return h.hexdigest()


def _reads_files(arg) -> bool:
    arg = str(arg)
    return any(arg == o or arg.startswith(o + '=') if o.startswith('--') else arg.startswith(o)
               for o in _FILE_ARGS)


def _file_digest(path):
    try:
        return _sha(Path(path).read_bytes())
    except OSError:
        return None


def _stat(path):
    try:
        st = os.stat(path)
        return [st.st_size, st.st_mtime_ns]
    except OSError:
        return None


def _key(input_md, text, metadata, kwargs):
    src_dir = Path(input_md).resolve().parent
    files = []
    preamble = metadata.get('preamble') or []
    for item in preamble if isinstance(preamble, list) else [preamble]:
        item = str(item)
        if not (item.startswith('\\') or '\n' in item):
            files.append(src_dir / item)
    template = kwargs.get('template') or metadata.get('template')
    if template:
        files.append(Path(texmark.__file__).resolve().parent / template)
    payload = {
        'env': _environment(), 'cwd': os.getcwd(),
        'input': str(Path(input_md).resolve()), 'text': _sha(text.encode()),
        'kwargs': kwargs, 'files': {str(f): _file_digest(f) for f in files},
    }
    return _sha(json.dumps(payload, sort_keys=True, default=str).encode())


def _image_urls(node):
    """Yield the URL of every Image in a pandoc JSON AST."""
    if isinstance(node, dict):
        if node.get('t') == 'Image':
            yield node['c'][2][0]
        for v in node.values():
            yield from _image_urls(v)
    elif isinstance(node, list):
        for v in node:
            yield from _image_urls(v)


def _record(input_md, text, output_tex, kwargs):
    """Figures read (deps) and files written (outputs) by the build just done."""
    build_dir = Path(kwargs.get('build_dir') or 'build').resolve()
    source_dir = Path(input_md).resolve().parent
    project_root = Path(kwargs.get('project_root') or '.').resolve()
    deps, outputs = {}, {}
    for url in _image_urls(json.loads(parse_markdown(text))):
        if not url or url.lower().endswith('.md') or url.startswith('data:'):
            continue
        if url.startswith(('http://', 'https://')):
            outputs[os.path.join('figures', safe_filename_from_url(url))] = None
            continue
        p = project_root / url.lstrip('/') if url.startswith('/') else source_dir / url
        deps[str(p.resolve())] = _stat(p)
    for rel in resolve_image_paths.url_map.values():
        outputs[rel] = None
    for rel in outputs:
        st = _stat(build_dir / rel)
        outputs[rel] = st and st[0]
    outputs = {rel: size for rel, size in outputs.items() if size is not None}
    tex = Path(output_tex).resolve()
    return deps, {'tex': [str(tex), _file_digest(tex)], 'files': outputs}


def _up_to_date(entry, key, kwargs):
    if entry.get('key') != key:
        return False
    if any(_stat(p) != st for p, st in entry['deps'].items()):
        return False
    tex_path, tex_sha = entry['outputs']['tex']
    if tex_sha is None or _file_digest(tex_path) != tex_sha:
        return False
    build_dir = Path(kwargs.get('build_dir') or 'build')
    return all((s := _stat(build_dir / rel)) and s[0] == size
               for rel, size in entry['outputs']['files'].items())


def _load(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def _save(path, entry):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(entry))
    os.replace(tmp, path)


def cached_build_tex(build_tex, input_md, output_tex, *, enabled=True, **kwargs):
    """Call ``build_tex(input_md, output_tex, **kwargs)`` unless the cache
    entry for ``output_tex`` shows that it would write the same file."""
    text = Path(input_md).read_text()
    metadata = load_markdown(text).metadata
    if (not enabled or kwargs.get('filters') or metadata.get('filters')
            or kwargs.get('filters_module') or metadata.get('filters_module')
            or any(_reads_files(a) for a in metadata.get('pandoc_args') or [])):
        return build_tex(input_md, output_tex, **kwargs)
    entry_path = Path(kwargs.get('build_dir') or 'build') / CACHE_DIR / f'{Path(output_tex).stem}.json'
    key = _key(input_md, text, metadata, kwargs)
    entry = _load(entry_path)
    try:
        if isinstance(entry, dict) and _up_to_date(entry, key, kwargs):
            logger.debug(f'reusing {Path(output_tex).name} (unchanged)')
            return None
    except (KeyError, TypeError, ValueError):
        pass
    result = build_tex(input_md, output_tex, **kwargs)
    deps, outputs = _record(input_md, text, output_tex, kwargs)
    _save(entry_path, {'key': key, 'deps': deps, 'outputs': outputs})
    return result


def cached_embed_scan(build_dir):
    """An embed scanner for ``resolve_project`` that keeps its results in
    ``build_dir``, keyed by the file's text and path and ``_environment()``."""
    def scan(markdown_path):
        path = Path(markdown_path).resolve()
        key = _sha(json.dumps([_environment(), str(path), path.read_text()]).encode())
        entry_path = Path(build_dir) / CACHE_DIR / f'{path.stem}.embeds.json'
        entry = _load(entry_path)
        if isinstance(entry, dict) and entry.get('key') == key and isinstance(entry.get('embeds'), list):
            return [Path(p) for p in entry['embeds']]
        found = _scan_ast_for_embeds(path)
        _save(entry_path, {'key': key, 'embeds': [str(p) for p in found]})
        return found
    return scan
