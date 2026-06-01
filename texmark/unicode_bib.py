"""Rewrite ``.bib`` files in place during the copy-to-build step so every
non-ASCII codepoint is replaced with its LaTeX equivalent.

Why this exists
---------------
pdflatex can read UTF-8 source but its 8-bit font stack has no glyph
slot for arbitrary codepoints. Anything outside inputenc's default
mapping table (Latin-Extended-A plus a handful of common symbols)
fails at compile time with::

    ! LaTeX Error: Unicode character X (U+XXXX)
                   not set up for use with LaTeX.

In ``-interaction=nonstopmode`` pdflatex drops the offending character
and keeps going — silently lossy. Bibliographies are the typical
breeding ground because ``bibtex`` copies ``.bib`` field bytes straight
into the ``.bbl`` with no Unicode handling of its own.

What this module does
---------------------
On every build, when texmark stages the bibliography into ``build_dir``,
the staged copy passes through :func:`rewrite_text` which walks every
non-ASCII codepoint and substitutes the LaTeX equivalent reported by
``pylatexenc``. The original ``.bib`` is untouched; only the build-dir
copy is rewritten. Codepoints pylatexenc can't translate are left in
place and reported via :func:`warn_unmapped` so the user knows which
specific entries will be lossy in the final PDF.

Engine considerations
---------------------
The rewrite is harmless under lualatex/xelatex (those engines accept
both raw UTF-8 and LaTeX commands), so it runs unconditionally. If
``pylatexenc`` isn't installed, the staged copy is identical to the
source — same behaviour as before this module existed.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from texmark.logs import logger

try:
    from pylatexenc.latexencode import unicode_to_latex  # type: ignore
except ImportError:  # pragma: no cover - exercised only when dep is absent
    unicode_to_latex = None


_NON_ASCII_RE = re.compile(r'[^\x00-\x7F]')
_ENTRY_RE = re.compile(r'^[ \t]*@\w+\s*\{\s*([^,\s}]+)', re.MULTILINE)


def _entry_at_offset(text: str, offset: int) -> str | None:
    """Entry key of the ``@type{key,...}`` block preceding ``offset``, if any."""
    last_key = None
    for m in _ENTRY_RE.finditer(text):
        if m.start() > offset:
            break
        last_key = m.group(1)
    return last_key


def rewrite_text(text: str) -> tuple[str, list[tuple[int, int, str | None]]]:
    """Replace every non-ASCII codepoint in ``text`` with its LaTeX form.

    Returns ``(rewritten_text, unmapped)``. ``unmapped`` is a list of
    ``(codepoint, line_number, entry_key)`` tuples for codepoints
    pylatexenc declined to translate (it returned the input unchanged);
    those characters are left in place in ``rewritten_text``, since
    silently deleting them would be worse than the existing pdflatex
    behaviour.

    If ``pylatexenc`` is unavailable, returns ``(text, [])`` — the file
    is staged unchanged.
    """
    if unicode_to_latex is None or not _NON_ASCII_RE.search(text):
        return text, []

    out_parts: list[str] = []
    unmapped: list[tuple[int, int, str | None]] = []
    last = 0
    for m in _NON_ASCII_RE.finditer(text):
        out_parts.append(text[last:m.start()])
        char = m.group(0)
        replacement = unicode_to_latex(char)
        if replacement == char:
            # pylatexenc couldn't translate this codepoint. Keep the
            # original char and record it for warning. pdflatex will
            # drop it the way it did before.
            out_parts.append(char)
            line = text.count('\n', 0, m.start()) + 1
            entry = _entry_at_offset(text, m.start())
            unmapped.append((ord(char), line, entry))
        else:
            out_parts.append(replacement)
        last = m.end()
    out_parts.append(text[last:])
    return ''.join(out_parts), unmapped


def stage_bib(src: str | Path, dst_dir: str | Path) -> Path | None:
    """Copy ``src`` (a ``.bib`` file) into ``dst_dir``, rewriting non-ASCII
    chars to LaTeX equivalents on the way. Returns the destination path,
    or ``None`` if ``src`` doesn't exist.

    Warnings for unmappable codepoints are emitted as side effects via
    :func:`warn_unmapped` so callers don't need to thread them through.
    """
    src_path = Path(src)
    if not src_path.exists():
        return None
    dst_dir = Path(dst_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_path = dst_dir / src_path.name

    if unicode_to_latex is None:
        # pylatexenc not installed — fall back to plain copy so behaviour
        # matches the pre-feature world for users who don't want the dep.
        shutil.copy2(src_path, dst_path)
        return dst_path

    raw = src_path.read_text(encoding='utf-8', errors='replace')
    rewritten, unmapped = rewrite_text(raw)
    if rewritten == raw:
        # No conversions happened — plain copy preserves mtime for
        # downstream incremental tools (latexmk, etc.).
        shutil.copy2(src_path, dst_path)
    else:
        dst_path.write_text(rewritten, encoding='utf-8')
    warn_unmapped(unmapped, src_path)
    return dst_path


def warn_unmapped(unmapped: list[tuple[int, int, str | None]],
                  src_path: str | Path) -> None:
    """Emit a ``logger.warning`` per unmapped codepoint."""
    for cp, line, entry in unmapped:
        entry_str = f' in @entry{{{entry}}}' if entry else ''
        logger.warning(
            f'{src_path}:{line}: U+{cp:04X} ({chr(cp)!r}){entry_str} '
            f'has no LaTeX replacement and will be dropped from the PDF '
            f'under pdflatex. Fix by editing the .bib entry or switching '
            f'to engine: lualatex / xelatex.'
        )
