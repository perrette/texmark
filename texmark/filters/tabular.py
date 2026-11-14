import panflute as pf
from texmark.logs import logger
from texmark.shared import journal_template


_CELL_MARKER = '%TEXMARK-CELL-BREAK%'


def _batch_convert_cells(cell_contents):
    """Convert N panflute block lists to N LaTeX strings via ONE pandoc call.

    The straightforward per-cell ``pf.convert_text`` pattern spawns one
    pandoc subprocess per cell — ~5-15 ms each, hundreds of ms for a
    real-world table. Instead we splice the inputs into a single Doc
    separated by a unique LaTeX-comment RawBlock that pandoc passes through
    verbatim, then split the rendered output on the same marker.

    Empty inputs map to empty outputs. Result list length always matches
    the input length.
    """
    if not cell_contents:
        return []
    blocks = []
    for i, content in enumerate(cell_contents):
        if i > 0:
            blocks.append(pf.RawBlock(_CELL_MARKER, format='latex'))
        blocks.extend(content or [])
    latex = pf.convert_text(blocks,
                            input_format='panflute',
                            output_format='latex',
                            extra_args=['--natbib'])
    return [part.strip() for part in latex.split(_CELL_MARKER)]


def _split_breaks(inlines):
    """``(inlines, broken)``: the inline list with each backslash of the text
    (``\\\\`` in the markdown, which pandoc reads as an escaped backslash) made
    a ``LineBreak``, the spaces around a line break dropped, and whether the
    list holds a line break (new, or one pandoc read itself)."""
    out = []
    for elem in inlines:
        if isinstance(elem, pf.Str) and '\\' in elem.text:
            for i, part in enumerate(elem.text.split('\\')):
                if i:
                    out.append(pf.LineBreak())
                if part:
                    out.append(pf.Str(part))
        else:
            out.append(elem)
    cleaned = []
    for i, elem in enumerate(out):
        if isinstance(elem, (pf.Space, pf.SoftBreak)) and (
                (cleaned and isinstance(cleaned[-1], pf.LineBreak))
                or (i + 1 < len(out) and isinstance(out[i + 1], pf.LineBreak))):
            continue
        cleaned.append(elem)
    return cleaned, any(isinstance(e, pf.LineBreak) for e in cleaned)


def _cell_breaks(blocks):
    """Apply ``_split_breaks`` to the paragraphs of a cell (in place);
    whether the cell has a line break."""
    broken = False
    for block in blocks:
        if isinstance(block, (pf.Plain, pf.Para)):
            content, b = _split_breaks(list(block.content))
            block.content = content
            broken |= b
    return broken


def _multiline(latex):
    """A cell with line breaks as a one-column tabular, so that the lines
    stack in the cell (what ``\\makecell`` does, without the package)."""
    return '\\begin{tabular}[t]{@{}l@{}}' + latex + '\\end{tabular}'


def _cite_filter(doc):
    """The journal's citation filter (e.g. ``\\cite`` for science), or None.
    It runs after this filter in the chain, too late for the cells, which
    are rendered here: apply it to them first."""
    from texmark import journals  # journals imports this module
    name = journals.canonical_template(journal_template(doc))
    return journals.JOURNALS.get(name, {}).get('cite')


def stringify_cell(cell):
    """Convert a single ``pf.TableCell``'s content to LaTeX.

    Retained for back-compat with any out-of-tree caller. For table-wide
    work prefer ``_batch_convert_cells`` so all cells share one subprocess.
    """
    return pf.convert_text(
        cell.content,
        input_format='panflute',
        output_format='latex',
        extra_args=['--natbib']
    )


def render_caption(caption):
    """Render a table caption to LaTeX, preserving inline formatting.

    ``pf.stringify`` would flatten the caption to plain text and drop the
    ``$...$`` math delimiters (as well as emphasis, citations, code, etc.).
    Rendering the caption's block content through pandoc keeps them intact.
    Whitespace (including pandoc's line wrapping) is collapsed so the result
    fits on a single ``\\caption{...}`` line.
    """
    if not caption or not caption.content:
        return ""
    latex = pf.convert_text(
        list(caption.content),
        input_format='panflute',
        output_format='latex',
        extra_args=['--natbib'],
    )
    return " ".join(latex.split())


def table_to_latex(elem, doc):

    if not isinstance(elem, pf.Table):
        return

    table_type = doc.get_metadata('table_type') or journal_template(doc)

    caption_text = render_caption(elem.caption)

    label = elem.identifier or ""

    header_rows = elem.head.content
    bodies = elem.content
    ncols = len(header_rows[0].content)

    # Collect every cell's content in document order so one pandoc call can
    # render them all. The slice indices below walk through the result in
    # the same order — header rows, then each body's rows.
    #
    # A backslash in the text of a cell (``\\\\`` in the markdown) is a line
    # break in that cell.
    cells_in_order = []
    for header_row in header_rows:
        for cell in header_row.content:
            cells_in_order.append(cell.content)
    for body in bodies:
        for row in body.content:
            for cell in row.content:
                cells_in_order.append(cell.content)
    cite = _cite_filter(doc)
    if cite is not None:
        for content in cells_in_order:
            for block in content:
                block.walk(cite, doc)
    broken = [_cell_breaks(content) for content in cells_in_order]
    rendered = _batch_convert_cells(cells_in_order)
    rendered = [_multiline(r) if b else r for r, b in zip(rendered, broken)]

    cursor = 0
    header_grid = []
    for header_row in header_rows:
        n = len(header_row.content)
        header_grid.append(rendered[cursor:cursor + n])
        cursor += n
    body_grids = []  # list of [ [row_cells, row_cells, ...], ... ] per body
    for body in bodies:
        body_rows = []
        for row in body.content:
            n = len(row.content)
            body_rows.append(rendered[cursor:cursor + n])
            cursor += n
        body_grids.append(body_rows)

    col_spec = 'l' * ncols
    lines = [r"\\"] if table_type == "science" else []
    lines.append('  ' + r"\tophline" if table_type == "copernicus" else '  ' + r"\hline")

    # Multi-row headers stack vertically per column (joined by newline so the
    # tabular gets a single header row with `\n`-separated lines in each cell).
    header_cells = ["\n".join(col_lines) for col_lines in zip(*header_grid)]
    lines.append('  ' + ' & '.join(header_cells) + r' \\')
    lines.append('  ' + r"\middlehline" if table_type == "copernicus" else '  ' + r"\hline")

    def _add_table_rule(lines):
        lines[-1] += r" [1ex]"

    for i, body_rows in enumerate(body_grids):
        if i > 0:
            _add_table_rule(lines)
        for row_cells in body_rows:
            if (all(c.strip() == "" for c in row_cells)
                    or all(c == "-" for c in row_cells)
                    or all(c == "---" for c in row_cells)):
                _add_table_rule(lines)
            else:
                lines.append('  ' + ' & '.join(row_cells) + r' \\')

    lines.append('  ' + r"\bottomhline" if table_type == "copernicus" else '  ' + r"\hline")

    table_lines = [
        r'\begin{table}[t]',
        r'\centering',
        rf'\caption{{{caption_text}}}',
        rf'\label{{{label}}}',
        rf'\begin{{tabular}}{{{col_spec}}}',
        *lines,
        r'\end{tabular}',
    ]
    if table_type == "copernicus":
        table_lines.append(r'\belowtable{}')
    table_lines.append(r'\end{table}')
    latex = '\n'.join(table_lines)

    return pf.RawBlock(latex, format='latex')

def main(doc=None):
    return pf.run_filter(table_to_latex, doc=doc)

if __name__ == "__main__":
    main()
