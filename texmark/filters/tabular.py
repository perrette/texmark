import panflute as pf
from texmark.logs import logger


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


def table_to_latex(elem, doc):

    table_type = doc.get_metadata('table_type') or doc.get_metadata('journal').get("template")

    if not isinstance(elem, pf.Table):
        return

    caption_text = pf.stringify(elem.caption) if elem.caption else ""

    label = elem.identifier or ""

    header_rows = elem.head.content
    bodies = elem.content
    ncols = len(header_rows[0].content)

    # Collect every cell's content in document order so one pandoc call can
    # render them all. The slice indices below walk through the result in
    # the same order — header rows, then each body's rows.
    cells_in_order = []
    for header_row in header_rows:
        for cell in header_row.content:
            cells_in_order.append(cell.content)
    for body in bodies:
        for row in body.content:
            for cell in row.content:
                cells_in_order.append(cell.content)
    rendered = _batch_convert_cells(cells_in_order)

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
