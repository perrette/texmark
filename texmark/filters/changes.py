"""Track changes: CriticMarkup spans as commands of the LaTeX ``changes``
package.

``texmark.criticmarkup`` turns CriticMarkup into bracketed spans, which pandoc
parses as Markdown (citations, cross-references, emphasis); its LaTeX writer
drops the span classes. This filter writes the spans with the classes
``added``, ``deleted``, ``highlight`` and ``comment`` as the commands of the
``changes`` package, loaded by texmark when the document's ``changes`` option
is on. The commands are written as ``\\chadded``, ``\\chdeleted``,
``\\chhighlight`` and ``\\chcomment``: texmark's preamble defines these as the
package's commands, which the package itself renames when another package
already defines ``\\comment`` or ``\\added`` (its
``commandnameprefix=ifneeded`` option).

    [new [@key]]{.added}                ->  \\chadded{new \\citep{key}}
    [new]{.added comment="13 Nov"}      ->  \\chadded[comment={13 Nov}]{new}
    [old]{.deleted}                     ->  \\chdeleted{old}

The ``comment`` attribute is escaped for LaTeX. With the option on, two other
notations mean the same: GFM strike-out ``~~old~~`` is a deletion, and the
HTML pair ``<ins>new</ins>`` / ``<del>old</del>`` (what GitHub renders) an
addition / deletion. With the option off, the four classes give the text with
the changes accepted (added and highlighted text kept as plain text, deleted
text and comments dropped; a heading, list item or paragraph left empty is
removed), strike-out is ulem's ``\\sout`` and HTML tags are left to pandoc.
"""
from __future__ import annotations

import panflute as pf

CHANGES_COMMANDS = ('added', 'deleted', 'highlight', 'comment')
_HTML_TAGS = {'ins': 'added', 'del': 'deleted'}
# Accepted text when the option is off: keep the content, or drop the span.
_ACCEPT = {'added': True, 'highlight': True, 'deleted': False, 'comment': False}
_LATEX_ESCAPES = {
    '\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%', '&': r'\&',
    '#': r'\#', '_': r'\_', '$': r'\$', '^': r'\textasciicircum{}',
    '~': r'\textasciitilde{}',
}


def changes_preamble(changes, strikeout=False):
    """The preamble lines for the ``changes`` option, and for strike-out
    (``\\sout``, from ulem, which the changes package also loads; with
    ``normalem`` so that ``\\emph`` stays italic)."""
    lines = []
    if changes or strikeout:
        lines.append('\\makeatletter\\@ifpackageloaded{ulem}{}'
                     '{\\usepackage[normalem]{ulem}}\\makeatother')
    if changes:
        lines.append('\\usepackage[commandnameprefix=ifneeded]{changes}')
        lines += [f'\\providecommand{{\\ch{c}}}{{\\{c}}}' for c in CHANGES_COMMANDS]
    return ''.join(line + '\n' for line in lines)


def latex_escape(text):
    return ''.join(_LATEX_ESCAPES.get(c, c) for c in text)


def changes_on(doc):
    """Whether the ``changes`` option of the document is on."""
    v = doc.get_metadata('changes', False)
    if isinstance(v, str):
        return v.strip().lower() not in ('false', 'off', 'no', '')
    return bool(v)


def _protect_cites(elem, doc):
    # The changes package reads its argument as a macro argument and strikes
    # deleted text out with ulem: some citation commands (apacite, scicite)
    # break in either case, and work inside ``\\mbox{\\protect ...}``.
    if isinstance(elem, pf.Cite):
        return [pf.RawInline('\\mbox{\\protect', format='latex'), elem,
                pf.RawInline('}', format='latex')]


def _change(cmd, attrs, content):
    """A changes-package command around ``content``. Footnotes cannot be
    typeset inside the argument; they are moved after the command."""
    notes = []

    def protect(elem, doc):
        if isinstance(elem, pf.Note):
            notes.append(elem)
            return []
        return _protect_cites(elem, doc)

    span = pf.Span(*content)
    span.walk(protect)
    return _wrap(cmd, attrs, list(span.content)) + notes


def _wrap(cmd, attrs, content):
    opt = ''
    if attrs:
        opt = '[' + ', '.join(f'{k}={{{latex_escape(v)}}}' for k, v in attrs.items()) + ']'
    return [pf.RawInline('\\' + cmd + opt + '{', format='latex'),
            *content,
            pf.RawInline('}', format='latex')]


# Blocks removed when a deletion left them empty (changes off).
_EMPTIABLE = (pf.Para, pf.Plain, pf.Header, pf.ListItem, pf.BulletList,
              pf.OrderedList, pf.BlockQuote)
_BLANK = (pf.Space, pf.SoftBreak, pf.LineBreak)


def _emptied(doc):
    # ids of the elements a dropped span or block was in, during this walk.
    if not hasattr(doc, '_texmark_emptied'):
        doc._texmark_emptied = set()
    return doc._texmark_emptied


def track_changes(elem, doc):
    if isinstance(elem, pf.Span) and elem.classes:
        cls = next((c for c in elem.classes if c in CHANGES_COMMANDS), None)
        if cls is None:
            return
        if not changes_on(doc):
            if _ACCEPT[cls]:
                return list(elem.content)
            _emptied(doc).add(id(elem.parent))
            return []
        return _change('ch' + cls, elem.attributes, elem.content)
    if isinstance(elem, _EMPTIABLE):
        emptied = _emptied(doc)
        if id(elem) in emptied:
            emptied.discard(id(elem))
            if all(isinstance(e, _BLANK) for e in elem.content):
                emptied.add(id(elem.parent))
                return []
        return
    if isinstance(elem, pf.Strikeout):
        if not changes_on(doc):
            return _change('sout', {}, elem.content)
        return _change('chdeleted', {}, elem.content)
    if not changes_on(doc):
        return
    if isinstance(elem, pf.RawInline) and elem.format == 'html':
        inner = elem.text.strip('<>/ ')
        tag = inner.split()[0].lower() if inner else ''
        if tag in _HTML_TAGS:
            if elem.text.startswith('</'):
                return pf.RawInline('}', format='latex')
            return pf.RawInline('\\ch' + _HTML_TAGS[tag] + '{', format='latex')
