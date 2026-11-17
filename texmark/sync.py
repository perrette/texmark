"""Forward and backward search between Markdown sources and the PDF.

    texmark sync forward  SOURCE.md:LINE[:COL] [--pdf PDF]
    texmark sync backward --pdf PDF PAGE X Y

Both print JSON. ``forward`` gives the place of a Markdown line in the PDF,
``{"page", "x", "y", "width", "height"}`` in PDF points with the origin at
the top left of the page, as ``synctex view`` gives them (a list when there
are several places). ``backward`` gives the Markdown line of a point of the
PDF, ``{"file", "line", "column"}`` (column is null). On error, the exit
status is 1 and the output is ``{"error": message, "code": code}``, with code
one of ``no-map``, ``no-pdf``, ``no-synctex``, ``stale``, ``not-in-map``,
``not-found``, ``synctex``.

They use the PDF's ``.synctex.gz`` (PDF ↔ .tex lines, through the
``synctex`` command) and its ``.srcmap.json`` (.tex ↔ Markdown lines, see
texmark.srcmap). The map gives, for each heading, its Markdown and .tex
line; between two headings, the line is the one whose words best match
(LaTeX commands and accents left out), or else is interpolated.

The same functions are available in Python: ``forward`` and ``backward``,
which raise ``SyncError``.

This module only imports the standard library and texmark.srcmap, so that
the command starts fast: it runs on each click in an editor.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from texmark import srcmap as _srcmap


class SyncError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------------------
# The map and the PDF
# ---------------------------------------------------------------------------

def load_map(pdf):
    """The map published with ``pdf``, checked against it."""
    pdf = Path(pdf)
    if not pdf.exists():
        raise SyncError('no-pdf', f'no PDF {pdf}')
    path = _srcmap.map_file(pdf)
    try:
        m = json.loads(path.read_text())
    except FileNotFoundError:
        raise SyncError('no-map', f'no source map {path}') from None
    except (OSError, ValueError) as e:
        raise SyncError('no-map', f'unreadable source map {path}: {e}') from None
    if (m.get('pdf_size') != pdf.stat().st_size
            or m.get('build') != _srcmap.pdf_digest(pdf)):
        raise SyncError('stale', f'the source map {path} is not that of {pdf} '
                                 '(a build did not finish?)')
    return m


def _candidate_maps(source):
    """Maps in the build folders above ``source`` (see find_pdf)."""
    d = Path(source).resolve().parent
    seen = []
    for _ in range(6):
        for pattern in ('*.srcmap.json', 'build*/*.srcmap.json'):
            seen.extend(sorted(d.glob(pattern)))
        if (d / '.git').exists() or d.parent == d:
            break
        d = d.parent
    return seen


def find_pdf(source):
    """The PDF whose map lists ``source``: in the folder of ``source`` or
    one above it (up to the git root), directly or in a ``build*`` folder;
    the most recent PDF when several do."""
    md = _srcmap.realpath(source)
    found = []
    for path in _candidate_maps(source):
        try:
            m = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if any(u.get('md') == md for u in m.get('units', [])):
            pdf = path.with_name(m.get('pdf') or path.name[:-len('.srcmap.json')] + '.pdf')
            if pdf.exists():
                found.append((pdf.stat().st_mtime, pdf))
    if not found:
        raise SyncError('no-map', f'no source map lists {source}; build the document, '
                                  'or give --pdf')
    return max(found)[1]


# ---------------------------------------------------------------------------
# Line matching
# ---------------------------------------------------------------------------

_TEX_ACCENT = re.compile(r"""\\[`'^"~=.uvHcdbtrk](?:\{(\w)\}|\s*(\w))""")
_TEX_COMMAND = re.compile(r'\\[A-Za-z@]+\*?')
_MD_URL = re.compile(r'\]\([^)]*\)|<https?://[^>]*>|https?://\S+')
_WORD = re.compile(r'[^\W\d_]+|\d+')


def _strip_accents(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', s)
                   if not unicodedata.combining(c))


def md_words(line):
    """The words of a Markdown line, in order, lower case, without accents."""
    line = _MD_URL.sub(']', line)
    return _WORD.findall(_strip_accents(line).lower())


def tex_words(line):
    """The words of a TeX line, without commands, comments and accents."""
    line = re.sub(r'(?<!\\)%.*', '', line)
    line = _TEX_ACCENT.sub(lambda m: m.group(1) or m.group(2), line)
    line = _TEX_COMMAND.sub(' ', line)
    return _WORD.findall(_strip_accents(line).lower())


def _anchors(unit):
    """(md line, tex line) pairs: the unit's start, its headings and its
    end, in increasing order on both sides. A heading on the unit's first
    TeX line replaces the start."""
    pts = [(unit['line'][0], unit['texline'][0])]
    for s in sorted(unit.get('sections', []), key=lambda s: s['line']):
        if len(pts) == 1 and s['texline'] == pts[0][1] and s['line'] >= pts[0][0]:
            pts[0] = (s['line'], s['texline'])
        elif s['line'] > pts[-1][0] and s['texline'] > pts[-1][1]:
            pts.append((s['line'], s['texline']))
    end = (unit['line'][1] + 1, unit['texline'][1] + 1)
    if end[0] > pts[-1][0] and end[1] > pts[-1][1]:
        pts.append(end)
    else:
        pts.append((max(end[0], pts[-1][0] + 1), max(end[1], pts[-1][1] + 1)))
    return pts


def _segment(pts, value, side):
    """The anchors (a, b) with a[side] <= value < b[side] (the first pair
    for a value before the first anchor)."""
    if value < pts[0][side]:
        return pts[0], pts[1]
    for a, b in zip(pts, pts[1:]):
        if a[side] <= value < b[side]:
            return a, b
    return pts[-2], pts[-1]


def _best_line(words, lines, first, last, guess, words_of):
    """The line in [first, last] of ``lines`` (1-based) that best matches the
    word list ``words``: the longest run of the same words in the same order,
    then the most words in common, then the nearest to ``guess``. ``guess``
    when no line shares a word."""
    best, best_key = guess, (0, 0, 0)
    if not words:
        return best
    wordset = set(words)
    for n in range(max(first, 1), min(last, len(lines)) + 1):
        other = words_of(lines[n - 1])
        common = len(wordset.intersection(other))
        if not common:
            continue
        run = SequenceMatcher(None, words, other, autojunk=False).find_longest_match(
            0, len(words), 0, len(other)).size
        key = (run, common, -abs(n - guess))
        if key > best_key:
            best, best_key = n, key
    return best


def _interpolate(value, a, b, side):
    other = 1 - side
    if b[side] - a[side] <= 0 or value <= a[side]:
        return a[other]
    frac = (value - a[side]) / (b[side] - a[side])
    return a[other] + int(round(frac * (b[other] - a[other] - 1)))


def md_to_tex(unit, line, md_lines, tex_lines):
    pts = _anchors(unit)
    for md, tex in pts:
        if md == line:
            return tex
    a, b = _segment(pts, line, 0)
    guess = _interpolate(line, a, b, 0)
    return _best_line(md_words(md_lines[line - 1]) if 0 < line <= len(md_lines) else [],
                      tex_lines, a[1], b[1] - 1, guess, tex_words)


def tex_to_md(unit, texline, md_lines, tex_lines):
    pts = _anchors(unit)
    for md, tex in pts:
        if tex == texline:
            return md
    a, b = _segment(pts, texline, 1)
    guess = _interpolate(texline, a, b, 1)
    return _best_line(tex_words(tex_lines[texline - 1]) if 0 < texline <= len(tex_lines) else [],
                      md_lines, a[0], b[0] - 1, guess, md_words)


def _lines(path):
    try:
        return Path(path).read_text(errors='replace').splitlines()
    except OSError:
        return []


# ---------------------------------------------------------------------------
# synctex
# ---------------------------------------------------------------------------

def _synctex(args):
    exe = shutil.which('synctex')
    if exe is None:
        raise SyncError('synctex', 'the synctex command is not installed')
    r = subprocess.run([exe] + args, capture_output=True, text=True)
    if r.returncode != 0:
        raise SyncError('synctex', (r.stderr or r.stdout).strip() or 'synctex failed')
    return r.stdout


def _records(out):
    """The records of ``synctex view`` or ``synctex edit`` output: dicts of
    their ``key:value`` lines; each record starts with ``Output:``."""
    records = []
    for line in out.splitlines():
        key, sep, value = line.partition(':')
        if not sep:
            continue
        if key == 'Output':
            records.append({})
        if records:
            records[-1].setdefault(key, value)
    return records


def _check_synctex(pdf):
    if not Path(pdf).with_name(Path(pdf).stem + '.synctex.gz').exists():
        raise SyncError('no-synctex', f'no SyncTeX file next to {pdf} '
                                      '(built with --no-synctex?)')


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def forward(source, line, column=None, pdf=None):
    """Places in the PDF of line ``line`` of the Markdown file ``source``:
    a list of ``{"page", "x", "y", "width", "height"}`` (PDF points, origin
    at the top left of the page, as ``synctex view`` gives them).
    ``column`` is accepted for the CLI's SOURCE:LINE:COL and not used: the
    place is that of the line."""
    pdf = Path(pdf) if pdf else find_pdf(source)
    m = load_map(pdf)
    _check_synctex(pdf)
    md = _srcmap.realpath(source)
    units = [u for u in m['units'] if u['md'] == md]
    if not units:
        raise SyncError('not-in-map', f'{source} is not typeset in {pdf}')
    unit = units[0]
    # Lines of the front matter (not typeset) go to the start of the body.
    line = min(max(int(line), unit['line'][0]), unit['line'][1])
    tex_lines = _lines(unit['tex'])
    texline = md_to_tex(unit, line, _lines(md), tex_lines)
    out = _synctex(['view', '-i', f'{texline}:0:{unit["tex"]}', '-o', str(pdf)])
    places = []
    for r in _records(out):
        if 'Page' not in r:
            continue
        try:
            places.append({'page': int(r['Page']), 'x': float(r['x']), 'y': float(r['y']),
                           'width': float(r.get('W', 0)), 'height': float(r.get('H', 0))})
        except (KeyError, ValueError):
            continue
    if not places:
        raise SyncError('not-found', f'no place in {pdf} for {unit["tex"]}:{texline}')
    return places


def backward(pdf, page, x, y):
    """The Markdown line of the point (``x``, ``y``) of page ``page`` of
    ``pdf`` (PDF points, origin at the top left): ``{"file", "line",
    "column"}``, column None."""
    pdf = Path(pdf)
    m = load_map(pdf)
    _check_synctex(pdf)
    out = _synctex(['edit', '-o', f'{int(page)}:{float(x)}:{float(y)}:{pdf}'])
    for r in _records(out):
        if 'Input' not in r or 'Line' not in r:
            continue
        tex = _srcmap.realpath(r['Input'])
        texline = int(r['Line'])
        for u in m['units']:
            if u['tex'] == tex and u['texline'][0] <= texline <= u['texline'][1]:
                line = tex_to_md(u, texline, _lines(u['md']), _lines(tex))
                return {'file': u['md'], 'line': line, 'column': None}
        raise SyncError('not-found', f'{tex}:{texline} does not come from a Markdown '
                                     'source (template?)')
    raise SyncError('not-found', f'no source for page {page} at ({x}, {y}) in {pdf}')


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

_SOURCE = re.compile(r'^(.*?):(\d+)(?::(\d+))?$')


def _parser():
    p = argparse.ArgumentParser(prog='texmark sync',
                                description='Forward and backward search between the '
                                            'Markdown sources and the PDF (JSON output).')
    sub = p.add_subparsers(dest='direction', required=True)
    f = sub.add_parser('forward', help='Markdown line -> place in the PDF')
    f.add_argument('source', metavar='SOURCE.md:LINE[:COL]')
    f.add_argument('--pdf', help='the PDF (default: the most recent one whose source map '
                                 'lists SOURCE, in build folders above it)')
    b = sub.add_parser('backward', help='point in the PDF -> Markdown line')
    b.add_argument('--pdf', required=True)
    b.add_argument('page', type=int)
    b.add_argument('x', type=float)
    b.add_argument('y', type=float)
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.direction == 'forward':
            m = _SOURCE.match(args.source)
            if not m:
                raise SyncError('usage', f'expected SOURCE.md:LINE[:COL], got {args.source!r}')
            places = forward(m.group(1), int(m.group(2)),
                             int(m.group(3)) if m.group(3) else None, args.pdf)
            result = places[0] if len(places) == 1 else places
        else:
            result = backward(args.pdf, args.page, args.x, args.y)
    except SyncError as e:
        print(json.dumps({'error': e.message, 'code': e.code}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
