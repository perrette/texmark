"""texmark-equations: numbered, labelled display equations.

The model is one rule: **a class on a display-math block names the LaTeX outer
environment to wrap it in.** Nothing texmark-specific to learn -- if you know
LaTeX's math environments, you know the vocabulary.

    $$ B $$                      ->  \\[ B \\]                      (unnumbered)
    $$ B $$ {.equation}          ->  \\begin{equation} B \\end{equation}
    $$ B $$ {.align}             ->  \\begin{align} B \\end{align}
    $$ B $$ {.gather}            ->  \\begin{gather} B \\end{gather}
    $$ B $$ {#eq:foo}            ->  equation + \\label{eq:foo}   (label => equation)
    $$ B $$ {#eq:foo .align}     ->  align    + \\label{eq:foo}

The ``{...}`` trailer attaches across any whitespace -- same line as the closing
``$$``, the next line, or after a blank line. The blank-line form is recommended:
GitHub only renders a ``$$…$$`` block when the closing ``$$`` ends its line, so
keeping the delimiter clean lets the equation render on GitHub too.

    $$
    \\begin{aligned} … \\end{aligned}
    $$

    {#eq:foo .align}
    where the symbols mean …

**Paragraph flow.** A display equation never starts or ends a paragraph on its
own: the prose before it, the equation, its trailer, and the prose after the
trailer are kept in one paragraph. The blank lines a ``$$`` block needs in
Markdown therefore do not become spurious ``\\par`` breaks around the equation.
A new paragraph starts only where you put a blank line *after* the trailer's
prose. (An equation with no prose before it -- e.g. the first thing under a
heading -- has nothing to merge into and stays its own paragraph.)

Same-document cross-references -- written ``@eq:foo`` or ``[](#eq:foo)`` -- are
rewritten to ``\\eqref{eq:foo}``. The same syntax works for figures (``fig:``),
tables (``tbl:``) and sections (``sec:``), which resolve to a bare ``\\ref`` (a
number like "Figure 3", not the parenthesised "(3)" used for equations).

The body is wrapped verbatim, with one deliberate exception: the **alignment
family** (``align``/``flalign``/``alignat``) processes ``&``/``\\\\`` itself, so an
inner ``\\begin{aligned}`` would nest redundantly and collapse the per-row
numbering back to a single number. Since multi-line math must be written as
``aligned`` to render in the KaTeX markdown preview, that inner wrapper is
stripped here so the rows land directly in the alignment environment -- giving
per-row numbering in the PDF *and* a working preview from the same source.

LaTeX's normal two-pass ``.aux`` resolution does the actual numbering, so the
filter never has to count anything itself.
"""
from __future__ import annotations

import re

import panflute as pf

from texmark.logs import logger

# One outer ``aligned`` wrapper, captured so it can be stripped for the
# alignment family (see module docstring).
_ALIGNED_RE = re.compile(
    r"^\s*\\begin\{aligned\}(?P<body>.*)\\end\{aligned\}\s*$", re.DOTALL
)
# A leading ``{...}`` group (optionally led by whitespace).
_ATTR_PREFIX_RE = re.compile(r"^\s*\{([^}]+)\}")

# Outer environments we recognise; anything else is passed through with a
# warning (likely a typo such as ``{.equaton}`` or an inner-only env like
# ``{.aligned}`` that errors standalone).
KNOWN_ENVS = {
    "equation", "align", "gather", "multline", "flalign", "alignat", "eqnarray",
}
# Alignment-family environments that handle ``&`` themselves, so a redundant
# inner ``aligned`` is unwrapped.
UNWRAP_ENVS = {"align", "flalign", "alignat"}

# Same-document cross-reference prefixes -> the LaTeX command they resolve to.
# Equations take ``\eqref`` (parenthesised, "(3)"); everything else takes a bare
# ``\ref`` ("Figure 3", "Table 2", "Section 4").
_REF_COMMANDS = {"eq": "eqref", "fig": "ref", "tbl": "ref", "sec": "ref"}

# Block containers whose child block-lists may hold an equation paragraph
# followed by a trailer paragraph that needs merging.
_BLOCK_CONTAINERS = (pf.Doc, pf.Div, pf.BlockQuote, pf.ListItem, pf.Note)


def _parse_attr(attr_string):
    """Return ``(identifier, classes)`` from a pandoc attr string such as
    ``#eq:foo .align``. Key=value attributes are ignored."""
    identifier = ""
    classes = []
    for token in attr_string.split():
        if token.startswith("#"):
            identifier = token[1:]
        elif token.startswith("."):
            classes.append(token[1:])
    return identifier, classes


def _inline_text(inline):
    """Text an inline contributes to an attr string, or ``None`` if it can't be
    part of one (so the search stops there). All whitespace -- spaces and soft/
    hard line breaks alike -- counts, so a trailer is found regardless of how the
    source happens to wrap between the ``$$`` and the ``{...}``."""
    if isinstance(inline, pf.Str):
        return inline.text
    if isinstance(inline, (pf.Space, pf.SoftBreak, pf.LineBreak)):
        return " "
    return None


def _take_attr_after_math(content, start):
    """Match a ``{...}`` attr group that immediately follows a Math (optionally
    separated by whitespace) and occupies whole inlines. Returns
    ``(attr_string, n_consumed)`` or ``(None, 0)``.

    Unlike an end-of-paragraph trailer search, the group need not end the
    paragraph -- prose may follow it (the equation flows on into the sentence).
    A ``{...}`` fused into the same Str as trailing text is left untouched.
    """
    text = ""
    for k in range(start, len(content)):
        piece = _inline_text(content[k])
        if piece is None:
            return None, 0
        text += piece
        stripped = text.lstrip()
        if stripped and not stripped.startswith("{"):
            return None, 0  # the first non-space thing after the math isn't a {
        if "}" in text:
            m = _ATTR_PREFIX_RE.match(text)
            if not m or text[m.end():].strip():
                return None, 0  # malformed, or {...} fused with trailing text
            return m.group(1), (k - start + 1)
    return None, 0


def _render_math(body, identifier, classes):
    """Return the RawInline that replaces a display-math block, or ``None`` to
    leave it as the default unnumbered ``\\[ ... \\]``.

    The environment is the first class given; a bare label (no class) implies
    ``equation``.
    """
    env = classes[0] if classes else ("equation" if identifier else None)
    if env is None:
        return None

    if env not in KNOWN_ENVS:
        logger.warning(
            f"texmark-equations: unknown math environment '{env}' "
            f"(from {{.{env}}}); passing through to LaTeX as-is."
        )

    if env in UNWRAP_ENVS:
        m = _ALIGNED_RE.match(body)
        if m:
            body = m.group("body")

    label = f"\\label{{{identifier}}}" if identifier else ""
    latex = f"\\begin{{{env}}}{label}{body}\\end{{{env}}}"
    return pf.RawInline(latex, format="latex")


def _rewrite_inlines(content):
    """Promote each display-math block (with its optional ``{...}`` trailer) to a
    LaTeX environment, in place within the inline stream. Returns
    ``(new_inlines, changed)``."""
    out = []
    i = 0
    changed = False
    n = len(content)
    while i < n:
        el = content[i]
        if isinstance(el, pf.Math) and el.format == "DisplayMath":
            attr, consumed = _take_attr_after_math(content, i + 1)
            identifier, classes = _parse_attr(attr) if attr is not None else ("", [])
            replacement = _render_math(el.text, identifier, classes)
            if replacement is not None:
                out.append(replacement)
                i += 1 + consumed  # drop the trailer inlines
                changed = True
                continue
            if attr is not None:
                out.append(el)  # recognised trailer, no promotion: drop the trailer
                i += 1 + consumed
                changed = True
                continue
        out.append(el)
        i += 1
    return out, changed


def _ref_command(identifier):
    """LaTeX ref command for a labelled-object identifier (``eq:…`` -> ``eqref``;
    ``fig:``/``tbl:``/``sec:`` -> ``ref``), or ``None`` when the prefix isn't a
    cross-reference prefix (e.g. a real citation key like ``smith2020``)."""
    prefix, sep, _rest = identifier.partition(":")
    if not sep:
        return None
    return _REF_COMMANDS.get(prefix)


def _ends_with_display_math(blk):
    return (
        isinstance(blk, pf.Para)
        and len(blk.content) > 0
        and isinstance(blk.content[-1], pf.Math)
        and blk.content[-1].format == "DisplayMath"
    )


def _starts_with_display_math(blk):
    if not isinstance(blk, pf.Para):
        return False
    for el in blk.content:
        if isinstance(el, (pf.Space, pf.SoftBreak, pf.LineBreak)):
            continue
        return isinstance(el, pf.Math) and el.format == "DisplayMath"
    return False


def _split_leading_attr(content):
    """If ``content`` begins with a ``{...}`` attr group carrying an id and/or
    classes, return ``(attr_string, rest_inlines)`` where ``rest`` is what
    follows the group (minus one separating whitespace inline); else
    ``(None, None)``.
    """
    text = ""
    for k in range(len(content)):
        piece = _inline_text(content[k])
        if piece is None:
            break
        text += piece
        if "}" in text:
            m = re.match(r"^\s*\{([^}]+)\}\s*$", text)
            if not m:
                break
            identifier, classes = _parse_attr(m.group(1))
            if not (identifier or classes):
                break
            rest = list(content[k + 1:])
            if rest and isinstance(rest[0], (pf.Space, pf.SoftBreak, pf.LineBreak)):
                rest = rest[1:]
            return m.group(1), rest
    return None, None


def _merge_trailer_blocks(blocks):
    """Fold the trailer paragraph that follows a display-math paragraph back onto
    the equation, **keeping the trailer's prose in the same paragraph** so no
    spurious break is introduced. Chains: a paragraph that ends in one equation
    and begins with the next equation's trailer is absorbed in sequence, and the
    chain stops at a trailer with nothing after it (a blank line then prose),
    which is where the author intends a new paragraph.
    """
    blocks = list(blocks)
    i = 0
    while i + 1 < len(blocks):
        blk, nxt = blocks[i], blocks[i + 1]
        if _ends_with_display_math(blk) and isinstance(nxt, (pf.Para, pf.Plain)):
            attr, rest = _split_leading_attr(list(nxt.content))
            if attr is not None:
                blk.content = (
                    list(blk.content)
                    + [pf.Space(), pf.Str("{" + attr + "}")]
                    + rest
                )
                del blocks[i + 1]
                continue  # blk may now end in the next equation -> re-check
        i += 1
    return blocks


def _merge_leading_equation_blocks(blocks):
    """Fold a paragraph that begins with a display equation into the preceding
    prose paragraph, so an equation never starts a paragraph. The blank line a
    ``$$`` block needs in Markdown is thus not turned into a ``\\par`` before the
    equation. (An equation with no prose before it -- e.g. first thing under a
    heading -- has nothing to merge into and is left as its own paragraph.)
    """
    result = []
    for blk in blocks:
        prev = result[-1] if result else None
        if (
            _starts_with_display_math(blk)
            and isinstance(prev, (pf.Para, pf.Plain))
        ):
            prev.content = list(prev.content) + [pf.Space()] + list(blk.content)
        else:
            result.append(blk)
    return result


class EquationsFilter:
    """Promote display math to numbered/labelled LaTeX environments and rewrite
    same-document equation references."""

    def prepare(self, doc):
        # Block pass first: fold blank-line-separated trailers (and the prose
        # after them) back onto the equation before the inline pass runs.
        self._merge_recursive(doc)

    def _merge_recursive(self, element):
        content = getattr(element, "content", None)
        if content is None:
            return
        for child in list(content):
            self._merge_recursive(child)
        if isinstance(element, _BLOCK_CONTAINERS):
            blocks = _merge_trailer_blocks(list(element.content))
            element.content = _merge_leading_equation_blocks(blocks)

    def action(self, elem, doc):
        # Same-document cross-references -- ``@prefix:id`` (a Cite) or
        # ``[](#prefix:id)`` (a Link) -- become \eqref/\ref. Cross-DOCUMENT
        # references (``[](other.md#id)``) are handled by the crossref filter.
        if isinstance(elem, pf.Cite):
            ids = [c.id for c in elem.citations]
            if len(ids) == 1:
                cmd = _ref_command(ids[0])
                if cmd:
                    return pf.RawInline(f"\\{cmd}{{{ids[0]}}}", format="latex")
            return None
        if isinstance(elem, pf.Link):
            url = elem.url or ""
            if url.startswith("#"):
                cmd = _ref_command(url[1:])
                if cmd:
                    return pf.RawInline(f"\\{cmd}{{{url[1:]}}}", format="latex")
            return None
        if isinstance(elem, (pf.Para, pf.Plain)):
            new, changed = _rewrite_inlines(list(elem.content))
            if changed:
                elem.content = new
        return None


equations_filter = EquationsFilter()


def main(doc=None):
    return pf.run_filter(
        equations_filter.action, prepare=equations_filter.prepare, doc=doc
    )


if __name__ == "__main__":
    main()
