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


# CrossRef-style ``.bib`` exports embed inline HTML markup in titles
# (``<i>δ</i><sup>18</sup>O``). bibtex passes those tags through verbatim
# and pdflatex renders ``<`` and ``>`` as the literal glyphs in
# the current font, which on the AMS template come out as "¡i¿".
# Convert the handful of inline tags that turn up in practice.
_HTML_TAG_MAP: dict[str, str] = {
    'i':      'textit',
    'em':     'emph',
    'b':      'textbf',
    'strong': 'textbf',
    'sup':    'textsuperscript',
    'sub':    'textsubscript',
    'scp':    'textsc',
    'tt':     'texttt',
    'u':      'underline',
}


def _rewrite_html_inline_tags(text: str) -> str:
    """Replace ``<tag>...</tag>`` pairs from the table above with their
    LaTeX command equivalents.

    Non-greedy matching handles nesting from the inside out across
    multiple tags (e.g. ``<i><sup>18</sup></i>`` becomes
    ``\\textit{\\textsuperscript{18}}``). Tags not in the table are left
    in place so a future user-defined tag doesn't get silently rewritten.
    """
    for tag, cmd in _HTML_TAG_MAP.items():
        pattern = re.compile(
            r'<' + tag + r'\b[^>]*>(.*?)</' + tag + r'>',
            re.IGNORECASE | re.DOTALL,
        )
        # Loop until stable so deeply nested same-tag uses converge:
        # <i>a<i>b</i>c</i> → \textit{a<i>b</i>c} → \textit{a\textit{b}c}
        prev = None
        while prev != text:
            prev = text
            text = pattern.sub(
                lambda m, c=cmd: '\\' + c + '{' + m.group(1) + '}',
                text,
            )
    return text


# Codepoints pylatexenc doesn't translate but that come up routinely in
# scientific bibliographies — primarily Unicode super/subscript blocks
# (U+2070-U+208E). The Latin-1 superscripts ¹²³ (U+00B9, B2, B3) are also
# overridden here so a run like ¹⁸O renders consistently as
# \textsuperscript{1}\textsuperscript{8}O instead of mixing
# \textonesuperior with \textsuperscript{}.
_OVERRIDES: dict[int, str] = {
    0x00B2: r'\textsuperscript{2}',  # ²
    0x00B3: r'\textsuperscript{3}',  # ³
    0x00B9: r'\textsuperscript{1}',  # ¹
    0x2070: r'\textsuperscript{0}',  # ⁰
    0x2071: r'\textsuperscript{i}',  # ⁱ
    0x2074: r'\textsuperscript{4}',  # ⁴
    0x2075: r'\textsuperscript{5}',  # ⁵
    0x2076: r'\textsuperscript{6}',  # ⁶
    0x2077: r'\textsuperscript{7}',  # ⁷
    0x2078: r'\textsuperscript{8}',  # ⁸
    0x2079: r'\textsuperscript{9}',  # ⁹
    0x207A: r'\textsuperscript{+}',  # ⁺
    0x207B: r'\textsuperscript{-}',  # ⁻
    0x207C: r'\textsuperscript{=}',  # ⁼
    0x207D: r'\textsuperscript{(}',  # ⁽
    0x207E: r'\textsuperscript{)}',  # ⁾
    0x207F: r'\textsuperscript{n}',  # ⁿ
    0x2080: r'\textsubscript{0}',    # ₀
    0x2081: r'\textsubscript{1}',    # ₁
    0x2082: r'\textsubscript{2}',    # ₂
    0x2083: r'\textsubscript{3}',    # ₃
    0x2084: r'\textsubscript{4}',    # ₄
    0x2085: r'\textsubscript{5}',    # ₅
    0x2086: r'\textsubscript{6}',    # ₆
    0x2087: r'\textsubscript{7}',    # ₇
    0x2088: r'\textsubscript{8}',    # ₈
    0x2089: r'\textsubscript{9}',    # ₉
    0x208A: r'\textsubscript{+}',    # ₊
    0x208B: r'\textsubscript{-}',    # ₋
    0x208C: r'\textsubscript{=}',    # ₌
    0x208D: r'\textsubscript{(}',    # ₍
    0x208E: r'\textsubscript{)}',    # ₎
}


def _adjacent_super_sub_merge(text: str) -> str:
    """Collapse runs of ``\\textsuperscript{X}\\textsuperscript{Y}...`` (or
    the ``\\textsubscript`` equivalent) into a single block so a sequence
    like ¹⁸ renders as ``\\textsuperscript{18}`` rather than
    ``\\textsuperscript{1}\\textsuperscript{8}``. Purely cosmetic but it
    matches what a human would write."""
    def merge(cmd: str, body: str) -> str:
        pattern = re.compile(r'(?:\\' + cmd + r'\{([^{}]*)\})+')
        def repl(m: re.Match) -> str:
            joined = ''.join(re.findall(r'\\' + cmd + r'\{([^{}]*)\}', m.group(0)))
            return '\\' + cmd + '{' + joined + '}'
        return pattern.sub(repl, body)
    text = merge('textsuperscript', text)
    text = merge('textsubscript', text)
    return text


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
    # Rewrite inline HTML tags first. They're independent of the
    # Unicode conversion and can run even when pylatexenc is absent.
    text = _rewrite_html_inline_tags(text)

    if unicode_to_latex is None or not _NON_ASCII_RE.search(text):
        return _adjacent_super_sub_merge(text), []

    out_parts: list[str] = []
    unmapped: list[tuple[int, int, str | None]] = []
    last = 0
    for m in _NON_ASCII_RE.finditer(text):
        out_parts.append(text[last:m.start()])
        char = m.group(0)
        cp = ord(char)
        # Overrides patch pylatexenc's gaps for scientifically common chars
        # (Unicode super/sub-script blocks). Take precedence over pylatexenc
        # so a sequence like ¹⁸ maps consistently to one typography family.
        if cp in _OVERRIDES:
            out_parts.append(_OVERRIDES[cp])
        else:
            replacement = unicode_to_latex(char)
            if replacement == char:
                # pylatexenc couldn't translate this codepoint. Keep the
                # original char and record it for warning. pdflatex will
                # drop it the way it did before.
                out_parts.append(char)
                line = text.count('\n', 0, m.start()) + 1
                entry = _entry_at_offset(text, m.start())
                unmapped.append((cp, line, entry))
            else:
                out_parts.append(replacement)
        last = m.end()
    out_parts.append(text[last:])
    return _adjacent_super_sub_merge(''.join(out_parts)), unmapped


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
