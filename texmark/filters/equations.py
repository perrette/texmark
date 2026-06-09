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

Same-document references to a labelled equation -- ``@eq:foo`` (a Cite) or
``[](#eq:foo)`` (a Link) -- are rewritten to ``\\eqref{eq:foo}``.

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

# A ``{...}`` attribute trailer occupying the whole suffix after the math.
_ATTR_RE = re.compile(r"^\s*\{([^}]+)\}\s*$")
# One outer ``aligned`` wrapper, captured so it can be stripped for the
# alignment family (see module docstring).
_ALIGNED_RE = re.compile(
    r"^\s*\\begin\{aligned\}(?P<body>.*)\\end\{aligned\}\s*$", re.DOTALL
)

# Outer environments we recognise; anything else is passed through with a
# warning (likely a typo such as ``{.equaton}`` or an inner-only env like
# ``{.aligned}`` that errors standalone).
KNOWN_ENVS = {
    "equation", "align", "gather", "multline", "flalign", "alignat", "eqnarray",
}
# Alignment-family environments that handle ``&`` themselves, so a redundant
# inner ``aligned`` is unwrapped.
UNWRAP_ENVS = {"align", "flalign", "alignat"}


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
    """Text an inline contributes to a trailing attr string, or ``None`` if it
    can't be part of one (so the trailer search stops there)."""
    if isinstance(inline, pf.Str):
        return inline.text
    if isinstance(inline, pf.Space):
        return " "
    return None


def _take_attr_trailer(content, start):
    """If ``content[start:]`` forms a single ``{...}`` attr trailer (optionally
    led by whitespace), return ``(attr_string, n_consumed)``; else ``(None, 0)``.

    pandoc splits a trailer with internal whitespace (e.g. ``{.align #eq:foo}``)
    across several Str/Space inlines, so we join forward until the accumulated
    suffix matches a lone ``{...}`` group.
    """
    text = ""
    for k in range(start, len(content)):
        piece = _inline_text(content[k])
        if piece is None:
            return None, 0
        text += piece
        m = _ATTR_RE.match(text)
        if m:
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
    """Splice display-math blocks (with optional ``{...}`` trailer) into LaTeX
    environments. Returns ``(new_inlines, changed)``."""
    out = []
    i = 0
    changed = False
    n = len(content)
    while i < n:
        el = content[i]
        if isinstance(el, pf.Math) and el.format == "DisplayMath":
            attr, consumed = _take_attr_trailer(content, i + 1)
            identifier, classes = _parse_attr(attr) if attr is not None else ("", [])
            replacement = _render_math(el.text, identifier, classes)
            if replacement is not None:
                out.append(replacement)
                i += 1 + consumed  # drop the trailer Str(s)
                changed = True
                continue
            if attr is not None:
                # A trailer we recognised but chose not to promote: keep the
                # math, drop the now-handled trailer so it doesn't leak as text.
                out.append(el)
                i += 1 + consumed
                changed = True
                continue
        out.append(el)
        i += 1
    return out, changed


def equations_filter(elem, doc):
    # Same-document equation references -> \eqref.
    if isinstance(elem, pf.Cite):
        ids = [c.id for c in elem.citations]
        if len(ids) == 1 and ids[0].startswith("eq:"):
            return pf.RawInline(f"\\eqref{{{ids[0]}}}", format="latex")
        return None
    if isinstance(elem, pf.Link):
        url = elem.url or ""
        if url.startswith("#eq:"):
            return pf.RawInline(f"\\eqref{{{url[1:]}}}", format="latex")
        return None
    # Promote display math at the container level: the label is a sibling Str
    # following the Math, not an attribute on it.
    if isinstance(elem, (pf.Para, pf.Plain)):
        new, changed = _rewrite_inlines(list(elem.content))
        if changed:
            elem.content = new
    return None


def main(doc=None):
    return pf.run_filter(equations_filter, doc=doc)


if __name__ == "__main__":
    main()
