"""Figure and table presentation filters.

Identifier tagging (``tag_figures``, ``extract_table_identifier``), global
figure defaults (``apply_figure_defaults`` and the figure* sentinel
machinery), and per-template caption munging (``stringify_captions``).
"""

import re
from pathlib import Path

import panflute as pf

from texmark.logs import logger


def tag_figures(elem, doc):
    if isinstance(elem, pf.Figure):
        # if it does not already exist, add an identifier to the figure so that it can be referenced
        # in the text using \ref{fig:figure-id}
        # use the content image url as the identifier, e.g. /image/figure.png -> fig:figure
        if not elem.identifier:
            images = []
            def _gather(e, d):
                if isinstance(e, pf.Image):
                    images.append(e)
            elem.walk(_gather)
            if not images:
                return elem
            tag = f'fig:{Path(images[0].url).stem}'
            logger.info(fr"Tagging figure: {tag}")
            elem.identifier = tag
    return elem


ATTR_RE = re.compile(r'\s*\{([^}]+)\}\s*$')


def parse_attr_string(attr_string):
    identifier = ''
    classes = []
    attributes = {}
    for token in attr_string.split():
        if token.startswith('#'):
            identifier = token[1:]
        elif token.startswith('.'):
            classes.append(token[1:])
        elif '=' in token:
            key, val = token.split('=', 1)
            attributes[key] = val
    return identifier, classes, attributes


def extract_table_identifier(elem, doc):
    if not isinstance(elem, pf.Table):
        return

    cap = elem.caption
    if not cap or not cap.content:
        return

    # at the time of writing, the caption is ListContainer(Plain(...))
    if not (
        cap.content
        and len(cap.content) == 1
        and isinstance(cap.content[0], pf.Plain)
    ):
        logger.warning(f"Caption content is not a Plain block: {cap.content}")
        return

    inlines = cap.content[0].content
    if not inlines:
        return

    # Pandoc splits an attribute trailer that contains internal whitespace
    # (e.g. ``{#tab:1 width=50%}``) across multiple Str/Space inlines, so
    # we can't just look at the last Str. Walk backward from the end,
    # joining inline text until the accumulated suffix matches ATTR_RE
    # (a ``{...}`` group at end-of-string with no nested ``}``). The first
    # inline whose ``{`` opens the trailer marks the cut point.
    def _inline_text(inline):
        if isinstance(inline, pf.Str):
            return inline.text
        if isinstance(inline, pf.Space):
            return " "
        return pf.stringify(inline)

    suffix = ""
    cut = None  # index of the first inline that belongs to the trailer
    match = None
    for i in range(len(inlines) - 1, -1, -1):
        suffix = _inline_text(inlines[i]) + suffix
        m = ATTR_RE.search(suffix)
        if m:
            cut = i
            match = m
            break
        # Bail out early if we've passed a closing brace without finding
        # a match: any ``}`` in the suffix that isn't the trailer's closer
        # means the regex (which forbids nested ``}``) can never match by
        # extending further left.
        if "}" in suffix and not suffix.rstrip().endswith("}"):
            return

    if cut is None or match is None:
        return

    attr_string = match.group(1)
    identifier, classes, attributes = parse_attr_string(attr_string)

    # Determine where the ``{`` sits inside inlines[cut]. The regex match
    # spans the joined suffix; everything from inlines[cut] onward is part
    # of the trailer, but inlines[cut] may also contain caption text before
    # the ``{`` (rare, since pandoc usually separates with a Space).
    cut_inline_text = _inline_text(inlines[cut])
    # Position within ``suffix`` where the matched trailer starts.
    trailer_start_in_suffix = match.start()
    # Position within ``cut_inline_text`` where the trailer starts.
    trailer_start_in_cut = trailer_start_in_suffix
    head_inlines = list(inlines[:cut])
    prefix_in_cut = cut_inline_text[:trailer_start_in_cut]
    # Drop any trailing whitespace the regex consumed before the ``{``.
    prefix_in_cut = prefix_in_cut.rstrip()
    if prefix_in_cut:
        head_inlines.append(pf.Str(prefix_in_cut))

    cap.content[:] = [pf.Plain(*head_inlines)]

    if identifier:
        elem.identifier = identifier
    if classes:
        elem.classes.extend(classes)
    if attributes:
        elem.attributes.update(attributes)


def _science_bold_first_sentence(caption_text):
    """Wrap the first sentence of a rendered LaTeX caption in ``\\textbf{}``.

    Science requires the first sentence of every figure/table caption to be
    bold (per their submission guide). Operates on the LaTeX string after
    pandoc has rendered the panflute caption.
    """
    parts = caption_text.split(".")
    parts[0] = r"\textbf{" + parts[0] + r"}"
    return ".".join(parts)


# Per-template, post-render caption munging hooks. Each entry takes the
# rendered LaTeX caption string and returns the possibly-modified version.
#
# ─── To add a journal-specific caption tweak ───────────────────────────────
# Register a callable here keyed by the journal template name
# (e.g. ``"nature"``, ``"copernicus"``). The hook receives the caption
# already rendered as LaTeX and returns the modified string.
# ───────────────────────────────────────────────────────────────────────────
#
# Performance note: any template listed here triggers one pandoc subprocess
# *per figure/table* in stringify_captions, because the caption has to be
# rendered to LaTeX before the munger can run. Templates *not* listed take
# the fast path: pandoc renders the caption natively on the final
# json->latex pass, no extra subprocess. So only register a munger when the
# template genuinely needs string-level LaTeX surgery that can't be done
# via the panflute AST or via the journal's LaTeX class.
CAPTION_MUNGERS = {
    "science": _science_bold_first_sentence,
}


def stringify_captions(elem, doc):
    """Apply per-template caption tweaks (e.g. Science's bold first sentence).

    Templates not registered in ``CAPTION_MUNGERS`` take the fast path:
    pandoc renders the caption natively on the final json->latex pass — no
    per-caption pandoc subprocess.
    """
    if not isinstance(elem, (pf.Figure, pf.Table)) or not elem.caption:
        return

    template = doc.get_metadata('journal', {}).get("template")
    munger = CAPTION_MUNGERS.get(template)
    if munger is None:
        return  # fast path

    caption_text = pf.convert_text(elem.caption.content,
        input_format='panflute',
        output_format='latex',
        extra_args=['--natbib']
    )
    caption_text = munger(caption_text)
    elem.caption.content = [pf.RawBlock(caption_text, format='latex')]


FIGSTAR_BEGIN = '% TEXMARK-FIGSTAR-BEGIN'
FIGSTAR_END = '% TEXMARK-FIGSTAR-END'


def expand_figstar_sentinels(body):
    """Rewrite ``\\begin{figure}``/``\\end{figure}`` wrapped between
    ``FIGSTAR_BEGIN``/``FIGSTAR_END`` sentinels into ``figure*`` equivalents,
    then strip the sentinel comments. Called from build.py after pandoc
    renders the body to LaTeX. See ``apply_figure_defaults`` for the
    upstream emitter."""
    body = re.sub(
        re.escape(FIGSTAR_BEGIN) + r'\s*\\begin\{figure\}',
        r'\\begin{figure*}', body)
    body = re.sub(
        r'\\end\{figure\}\s*' + re.escape(FIGSTAR_END),
        r'\\end{figure*}', body)
    # Drop any sentinel that didn't pair with a figure (e.g. a downstream
    # filter dropped the figure but left the wrapper). They are valid LaTeX
    # comments either way, but removing them keeps the .tex tidy.
    body = re.sub(re.escape(FIGSTAR_BEGIN) + r'\n?', '', body)
    body = re.sub(re.escape(FIGSTAR_END) + r'\n?', '', body)
    return body


def apply_figure_defaults(elem, doc):
    """Apply global figure-width and figure-span metadata to figures.

    - `figure-width` (default `100%`) sets the default image width when none is
      given on the figure itself. Percent values are interpreted by pandoc as a
      fraction of `\\linewidth`, which inside `figure*` automatically expands
      to the full text width.
    - `figure-span` (default `column`) — when set to `full`, wrap the figure
      in sentinel RawBlocks. ``expand_figstar_sentinels`` (called from
      build.py after pandoc renders the body) rewrites the surrounding
      ``\\begin{figure}``/``\\end{figure}`` into ``figure*``. Doing it in
      post-render avoids one pandoc subprocess per full-span figure.
      Can be set globally via document metadata or per-figure via the image's
      attribute syntax: ``![cap](img){figure-span=full}``.
    """
    if not isinstance(elem, pf.Figure):
        return

    if not (elem.content and getattr(elem.content[0], 'content', None)):
        return
    target = elem.content[0].content[0]
    if not isinstance(target, pf.Image):
        return
    if "width" not in target.attributes:
        target.attributes['width'] = doc.get_metadata('figure-width', '100%')

    # Pandoc puts ``#id`` on the Figure but other ``{...}`` attributes on the
    # inner Image, so check both before falling back to the document default.
    span = (
        target.attributes.pop('figure-span', None)
        or elem.attributes.pop('figure-span', None)
        or doc.get_metadata('figure-span', 'column')
    )

    if span == 'full':
        return [
            pf.RawBlock(FIGSTAR_BEGIN, format='latex'),
            elem,
            pf.RawBlock(FIGSTAR_END, format='latex'),
        ]
