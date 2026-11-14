"""CriticMarkup to pandoc spans.

CriticMarkup (criticmarkup.com) is the Markdown convention for track changes:

    {++ added ++}      {-- deleted --}      {~~ old ~> new ~~}
    {>> comment <<}    {== highlight ==}

Pandoc does not read it (the marks are plain text to it, and ``--`` would even
become an en dash), so ``rewrite`` turns the marks into bracketed spans before
the text reaches pandoc, which then parses what is inside them (citations,
cross-references, emphasis) as usual:

    {++ new [@key] ++}              ->  [new [@key]]{.added}
    {-- old --}                     ->  [old]{.deleted}
    {~~ old ~> new ~~}              ->  [old]{.deleted}[new]{.added}
    {== text ==}                    ->  [text]{.highlight}
    {>> remark <<}                  ->  [remark]{.comment}
    {++ new ++}{>> why <<}          ->  [new]{.added comment="why"}

A comment directly after another mark (whitespace allowed) becomes that
span's ``comment`` attribute; on its own it is a span of its own. Padding
whitespace just inside the braces is dropped. The spans are rendered by
``texmark.filters.changes`` as the commands of the LaTeX ``changes`` package.

A mark never spans a blank line. A mark that covers a heading or list items
gives one span per line, inside the heading or item marker, so that the
heading or list is still one:

    {++ ## Results              ->  ## [Results]{.added}
    - item ++}                      - [item]{.added}

Square brackets inside a mark are escaped when they are unbalanced, so that
``{++ [ ++}`` stays one span; balanced ones are kept, so citations and links
inside a mark still work. The YAML front matter, fenced code blocks and inline
code are not rewritten. Marks in other places pandoc reads as code or raw
text (indented code blocks, math, raw LaTeX) are put back as written in the
parsed document by ``restore_code``.
"""
from __future__ import annotations

import re

# Content of a mark: lazy, not across a blank line.
_C = r'((?:(?!\n[ \t]*\n).)*?)'
_FLAGS = re.S

MARKS = re.compile(
    r'\{\+\+' + _C + r'\+\+\}'                      # 1 added
    r'|\{--' + _C + r'--\}'                         # 2 deleted
    r'|\{~~' + _C + r'~>' + _C + r'~~\}'            # 3 old, 4 new
    r'|\{==' + _C + r'==\}'                         # 5 highlight
    r'|\{>>' + _C + r'<<\}',                        # 6 comment
    _FLAGS)

_TRAILING_COMMENT = re.compile(r'[ \t]*\{>>' + _C + r'<<\}', _FLAGS)
# Opening fence: up to three spaces, then three or more backticks or tildes.
_FENCE = re.compile(r'^ {0,3}(`{3,}|~{3,})', re.M)
# Inline code: a run of backticks, the shortest content, the same run.
_INLINE_CODE = re.compile(r'(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)', re.S)
_PLACEHOLDER = '\x00{}\x00'
_PLACEHOLDER_RE = re.compile('\x00(\\d+)\x00')


def _balanced(text):
    depth, i = 0, 0
    while i < len(text):
        c = text[i]
        if c == '\\':
            i += 2
            continue
        if c == '[':
            depth += 1
        elif c == ']':
            depth -= 1
            if depth < 0:
                return False
        i += 1
    return depth == 0


def _escape_brackets(text):
    return re.sub(r'(?<!\\)([\[\]])', r'\\\1', text)


def _span(content, cls, comment=None):
    content = content.strip()
    if not _balanced(content):
        content = _escape_brackets(content)
    attrs = '.' + cls
    if comment is not None:
        comment = ' '.join(comment.split())
        attrs += ' comment="' + comment.replace('\\', '\\\\').replace('"', '\\"') + '"'
    return f'[{content}]{{{attrs}}}'


# Heading, list item or block quote marker at the start of a line.
_BLOCK_MARKER = re.compile(r'[ \t]*(?:#{1,6}[ \t]+|[-*+][ \t]+|\d+[.)][ \t]+|>[ \t]?)')


def _spans(content, cls, comment, at_line_start):
    """The spans of one mark: one span, or one per line when a line of the
    mark starts with a block marker (the marker is kept outside)."""
    lines = content.strip(' \t').split('\n')
    markers = [(_BLOCK_MARKER.match(line) if i or at_line_start else None)
               for i, line in enumerate(lines)]
    if not any(markers):
        return _span(content, cls, comment)
    out = []
    last = max(i for i, line in enumerate(lines) if line.strip())
    for i, (line, m) in enumerate(zip(lines, markers)):
        marker = m.group(0) if m else ''
        rest = line[len(marker):]
        if rest.strip():
            out.append(marker + _span(rest, cls, comment if i == last else None))
        else:
            out.append(line)
    return '\n'.join(out)


def _rewrite_segment(text, pairs):
    # Mask inline code so that marks inside it are left alone.
    codes = []

    def mask(m):
        codes.append(m.group(0))
        return _PLACEHOLDER.format(len(codes) - 1)

    def unmask(t):
        return _PLACEHOLDER_RE.sub(lambda m: codes[int(m.group(1))], t) if codes else t

    if '`' in text:
        text = _INLINE_CODE.sub(mask, text)
    out, pos = [], 0
    while True:
        m = MARKS.search(text, pos)
        if not m:
            break
        out.append(text[pos:m.start()])
        end = m.end()
        comment = None
        if m.lastindex != 6:
            c = _TRAILING_COMMENT.match(text, end)
            if c:
                comment, end = c.group(1), c.end()
        line_start = text.rfind('\n', 0, m.start()) + 1
        at_line_start = not text[line_start:m.start()].strip()
        if m.group(1) is not None:
            new = _spans(m.group(1), 'added', comment, at_line_start)
        elif m.group(2) is not None:
            new = _spans(m.group(2), 'deleted', comment, at_line_start)
        elif m.group(3) is not None:
            new = _span(m.group(3), 'deleted') + _span(m.group(4), 'added', comment)
        elif m.group(5) is not None:
            new = _spans(m.group(5), 'highlight', comment, at_line_start)
        else:
            new = _span(m.group(6), 'comment')
        out.append(new)
        pairs.append((unmask(new), unmask(text[m.start():end])))
        pos = end
    out.append(text[pos:])
    return unmask(''.join(out))


_FRONT_MATTER = re.compile(r'\A---[ \t]*\n.*?\n(?:---|\.\.\.)[ \t]*(?:\n|\Z)', re.S)


def rewrite_marks(text):
    """``(text, pairs)``: the text with CriticMarkup rewritten as spans, and
    the ``(span text, original mark)`` pair of each mark. The front matter,
    fenced code blocks and inline code are passed through."""
    pairs = []
    if '{' not in text:
        return text, pairs
    fm = _FRONT_MATTER.match(text)
    parts = [fm.group(0)] if fm else []
    pos, fence = (fm.end() if fm else 0), None
    for m in _FENCE.finditer(text, pos):
        run = m.group(1)
        if fence is None:
            parts.append(_rewrite_segment(text[pos:m.start()], pairs))
            fence, pos = run, m.start()
        elif run[0] == fence[0] and len(run) >= len(fence):
            # A closing fence: same character, at least as long.
            eol = text.find('\n', m.end())
            end = len(text) if eol < 0 else eol
            parts.append(text[pos:end])
            fence, pos = None, end
    if fence is not None:
        parts.append(text[pos:])
    else:
        parts.append(_rewrite_segment(text[pos:], pairs))
    return ''.join(parts), pairs


def rewrite(text):
    """``(text, found)``: the text with CriticMarkup rewritten as spans, and
    whether any mark was found."""
    text, pairs = rewrite_marks(text)
    return text, bool(pairs)


def found(text):
    """Whether the text contains any CriticMarkup mark (outside code)."""
    return bool(rewrite_marks(text)[1])


# Pandoc JSON elements whose text pandoc does not parse: (type, index of the
# text in "c").
_VERBATIM = {'Code': 1, 'CodeBlock': 1, 'Math': 1, 'RawInline': 1, 'RawBlock': 1}


def restore_code(node, pairs):
    """Put the marks back as written in the code, math and raw text of the
    pandoc JSON ``node`` (in place): pandoc did not read the spans there."""
    if isinstance(node, list):
        for item in node:
            restore_code(item, pairs)
    elif isinstance(node, dict):
        i = _VERBATIM.get(node.get('t'))
        if i is not None:
            text = node['c'][i]
            for new, old in pairs:
                if new in text:
                    text = text.replace(new, old)
            node['c'][i] = text
            return
        for value in node.values():
            if isinstance(value, (list, dict)):
                restore_code(value, pairs)
