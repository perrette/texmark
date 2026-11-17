"""The source map: Markdown lines ↔ lines of the generated .tex files.

SyncTeX links positions in the PDF to lines of the .tex files that LaTeX
read. ``<pdf-stem>.srcmap.json``, published next to the PDF (and its
``.synctex.gz``), links those .tex lines to the Markdown sources. Its format
is a contract for other tools (docs/synctex-design.md)::

    {
      "version": 1,
      "pdf": "thesis.pdf",
      "pdf_size": 1234567,
      "generated": "2026-11-17T12:00:00Z",
      "build": "sha256:<hex digest of the PDF>",
      "units": [
        {"md": "/abs/introduction.md", "line": [5, 410],
         "tex": "/abs/build/introduction.tex", "texline": [1, 380],
         "sections": [{"title": "Introduction", "line": 5, "texline": 1}]}
      ]
    }

One unit per source file that the PDF typesets: the root document (its body
in the master .tex) and each chapter (its whole .tex). ``line`` and
``texline`` are inclusive ranges, 1-based; ``line`` starts after the YAML
front matter. ``sections``: each heading's Markdown and TeX line. Paths are
absolute with symlinks resolved. ``build`` and ``pdf_size`` identify the PDF
the map was published with: a reader compares the size, then the hash.

How the sections are found: a scan of the Markdown gives the line of each
heading (ATX and setext; not in the front matter, fenced code or HTML
comments). They are matched in order to the Header blocks of pandoc's
document; when the counts differ, by their text. A heading's TeX line is
that of the sectioning command carrying its identifier (``\\label{id}``)
within the unit's TeX range; a heading that a filter moved out of the body
(e.g. an abstract section into the template's abstract) has none and is left
out. The CriticMarkup rewrite does not matter: the scan reads the text as
written, and the rewrite never moves a heading to another line.

A unit is computed from the Markdown text and the .tex file, and cached in
``<build>/.texmark-cache/<tex-stem>.srcmap.json`` keyed by both, so that a
chapter that texcache did not rebuild costs no pandoc parse.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

VERSION = 1
_UNIT_FORMAT = 1
CACHE_DIR = '.texmark-cache'

_FRONT_MATTER = re.compile(r'\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)', re.S)
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})')
_ATX = re.compile(r'^ {0,3}(#{1,6})(?:[ \t]+|$)')
_SETEXT = re.compile(r'^ {0,3}(=+|-+)[ \t]*$')
_SECTIONING = re.compile(
    r'\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)'
    r'\*?\s*(?:\[[^\]]*\])?\{')


def realpath(path) -> str:
    return os.path.realpath(path)


def map_file(pdf) -> Path:
    """The map that goes with ``pdf``: same directory and stem."""
    pdf = Path(pdf)
    return pdf.with_name(pdf.stem + '.srcmap.json')


# ---------------------------------------------------------------------------
# Markdown side
# ---------------------------------------------------------------------------

def body_start(text: str) -> int:
    """First line (1-based) after the YAML front matter."""
    m = _FRONT_MATTER.match(text)
    return m.group(0).count('\n') + 1 if m else 1


def scan_headings(text: str) -> list[tuple[int, str]]:
    """``(line, text)`` of the headings of a Markdown document, in order.

    Pandoc's markdown wants a blank line before a heading (or the start of
    the body); the front matter, fenced code blocks and HTML comments are
    skipped."""
    lines = text.split('\n')
    i = body_start(text) - 1
    out = []
    fence = None
    in_comment = False
    prev_blank = True
    while i < len(lines):
        line = lines[i]
        if fence:
            m = _FENCE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip().strip(fence[0]):
                fence = None
                prev_blank = False
            i += 1
            continue
        if in_comment:
            if '-->' in line:
                in_comment = False
            i += 1
            prev_blank = False
            continue
        stripped = line.strip()
        if not stripped:
            prev_blank = True
            i += 1
            continue
        m = _FENCE.match(line)
        if m:
            fence = m.group(1)
            i += 1
            continue
        if stripped.startswith('<!--'):
            in_comment = '-->' not in stripped[4:]
            prev_blank = False
            i += 1
            continue
        if prev_blank:
            m = _ATX.match(line)
            if m:
                out.append((i + 1, line[m.end():]))
            elif (i + 1 < len(lines) and _SETEXT.match(lines[i + 1])
                  and not line.startswith(('    ', '\t'))):
                out.append((i + 1, line))
                i += 2
                prev_blank = False
                continue
        prev_blank = False
        i += 1
    return out


def _stringify(node) -> str:
    """Plain text of pandoc JSON inlines."""
    if isinstance(node, list):
        return ''.join(_stringify(n) for n in node)
    if not isinstance(node, dict):
        return ''
    t, c = node.get('t'), node.get('c')
    if t == 'Str':
        return c
    if t in ('Space', 'SoftBreak', 'LineBreak'):
        return ' '
    if t in ('Code', 'Math'):
        return c[1]
    if t in ('Emph', 'Strong', 'Strikeout', 'Superscript', 'Subscript',
             'SmallCaps', 'Underline'):
        return _stringify(c)
    if t in ('Span', 'Link', 'Quoted', 'Cite'):
        return _stringify(c[1])
    if t == 'Image':
        return _stringify(c[1])
    return ''


def ast_headers(ast: dict) -> list[tuple[str, str]]:
    """``(identifier, plain text)`` of the Header blocks at the top level and
    in Divs, in order."""
    out = []

    def walk(blocks):
        for b in blocks:
            if b.get('t') == 'Header':
                out.append((b['c'][1][0], ' '.join(_stringify(b['c'][2]).split())))
            elif b.get('t') == 'Div':
                walk(b['c'][1])
    walk(ast.get('blocks', []))
    return out


def _norm(s: str) -> str:
    s = re.sub(r'\{[^}]*\}\s*$', '', s.strip())   # trailing {#id .class}
    s = re.sub(r'\s#+\s*$', '', s)                 # closing #s
    return re.sub(r'\W+', '', s).lower()


def match_headings(scanned, headers):
    """Pair scanned headings ``(line, text)`` with pandoc's headers
    ``(id, title)``: in order when the counts agree, else by text (in order).
    Returns ``[(line, id, title)]``."""
    if len(scanned) == len(headers):
        return [(line, hid, title) for (line, _), (hid, title) in zip(scanned, headers)]
    out = []
    j = 0
    for line, text in scanned:
        key = _norm(text)
        for k in range(j, len(headers)):
            if _norm(headers[k][1]) == key:
                out.append((line, headers[k][0], headers[k][1]))
                j = k + 1
                break
    return out


# ---------------------------------------------------------------------------
# TeX side
# ---------------------------------------------------------------------------

def _line_starts(text):
    starts = [0]
    for m in re.finditer('\n', text):
        starts.append(m.end())
    return starts


def _line_of(starts, pos):
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= pos:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


def tex_label(identifier: str) -> str:
    """The label pandoc's LaTeX writer gives an identifier (its ``toLabel``):
    ASCII letters, digits and ``_-+=:;.`` are kept, other characters become
    ``ux`` and their code point in hex."""
    return ''.join(c if (c.isascii() and c.isalnum()) or c in '_-+=:;.'
                   else f'ux{ord(c):x}' for c in identifier)


def tex_heading_lines(tex: str, ids, texline) -> dict:
    """Line of the sectioning command of each identifier in ``ids`` whose
    ``\\label{id}`` is within the lines ``texline`` (inclusive)."""
    starts = _line_starts(tex)
    first, last = texline
    lo = starts[first - 1] if first - 1 < len(starts) else len(tex)
    hi = starts[last] if last < len(starts) else len(tex)
    region = tex[lo:hi]
    commands = [m.start() + lo for m in _SECTIONING.finditer(region)]
    out = {}
    for hid in ids:
        if hid in out or not hid:
            continue
        i = region.find('\\label{' + tex_label(hid) + '}')
        if i < 0:
            continue
        pos = i + lo
        before = [c for c in commands if c <= pos]
        # The command that carries the label: the last one before it, on
        # the same line or a few lines up (a long title wraps).
        if before and _line_of(starts, pos) - _line_of(starts, before[-1]) <= 3:
            pos = before[-1]
        out[hid] = _line_of(starts, pos)
    return out


# ---------------------------------------------------------------------------
# Units and the map file
# ---------------------------------------------------------------------------

def _sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def compute_unit(md_path, tex_path, md_text, tex_text, texline=None, ast=None):
    """The unit of ``md_path`` typeset from ``tex_path`` (see module doc).
    ``texline``: the TeX lines of the body (default: the whole file).
    ``ast``: pandoc JSON of ``md_text`` (default: parse it)."""
    nlines = len(md_text.split('\n')) - (1 if md_text.endswith('\n') else 0)
    ntex = len(tex_text.split('\n')) - (1 if tex_text.endswith('\n') else 0)
    texline = list(texline) if texline else [1, max(ntex, 1)]
    if ast is None:
        from texmark.project import parse_markdown
        ast = json.loads(parse_markdown(md_text))
    matched = match_headings(scan_headings(md_text), ast_headers(ast))
    lines = tex_heading_lines(tex_text, [hid for _, hid, _ in matched], texline)
    sections = [{'title': title, 'line': line, 'texline': lines[hid]}
                for line, hid, title in matched if hid in lines]
    return {'md': realpath(md_path), 'line': [body_start(md_text), max(nlines, 1)],
            'tex': realpath(tex_path), 'texline': texline, 'sections': sections}


def unit(md_path, tex_path, texline=None, cache_dir=None):
    """``compute_unit`` from the files, through the cache in ``cache_dir``
    (no cache when None). None when a file is missing."""
    try:
        md_text = Path(md_path).read_text()
        tex_text = Path(tex_path).read_text(errors='replace')
    except OSError:
        return None
    key = _sha(json.dumps([_UNIT_FORMAT, realpath(md_path), realpath(tex_path),
                           texline, md_text, tex_text]))
    entry = Path(cache_dir) / f'{Path(tex_path).stem}.srcmap.json' if cache_dir else None
    if entry is not None:
        try:
            cached = json.loads(entry.read_text())
            if cached.get('key') == key:
                return cached['unit']
        except (OSError, ValueError, KeyError, AttributeError):
            pass
    u = compute_unit(md_path, tex_path, md_text, tex_text, texline)
    if entry is not None:
        try:
            entry.parent.mkdir(parents=True, exist_ok=True)
            _write_atomic(entry, json.dumps({'key': key, 'unit': u}))
        except OSError:
            pass
    return u


def _write_atomic(path, text):
    path = Path(path)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def pdf_digest(pdf) -> str:
    h = hashlib.sha256()
    with open(pdf, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return 'sha256:' + h.hexdigest()


def write_map(dst, pdf, pdf_name, units):
    """Write the map ``dst`` for the PDF file ``pdf`` (whose bytes are
    those of the published PDF ``pdf_name``), atomically."""
    data = {
        'version': VERSION,
        'pdf': pdf_name,
        'pdf_size': Path(pdf).stat().st_size,
        'generated': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'build': pdf_digest(pdf),
        'units': [u for u in units if u],
    }
    _write_atomic(dst, json.dumps(data, indent=1, ensure_ascii=False) + '\n')
