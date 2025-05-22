import panflute as pf
from texmark.logs import logger

def inlinemath_as_rawlatex(elem, doc):
    """Convert inline math to raw LaTeX."""
    if isinstance(elem, pf.Math):
        # Convert inline math to raw LaTeX
        return pf.RawInline(f"${pf.stringify(elem)}$", format='latex')
    return elem

def table_to_latex(elem, doc):

    if not isinstance(elem, pf.Table):
        return

    # Safely extract caption
    if elem.caption:
        caption_text = pf.stringify(elem.caption)

    label_ = elem.identifier or ("-".join([w for w in caption_text.split() if len(w) > 3][:3]).lower() if caption_text else None)
    label = f"tab:{label_}" if label_ else ""

    # 2. Extract header and rows
    headers = elem.head.content
    bodies = elem.content
    ncols = len(headers[0].content)

    def stringify_cell(cell):
        # logger.warning(f"stringify_cell: {cell}")
        return pf.stringify(cell)

    col_spec = 'l' * ncols
    lines = ['  ' + r"\tophline"]
    # Table header
    header_cells = ["\n".join([stringify_cell(line) for line in lines]) for lines in zip(*[h.content for h in headers])]
    lines.append('  ' + ' & '.join(header_cells) + r' \\')
    lines.append('  ' + r"\middlehline")

    def _add_table_rule(lines):
        # lines.append('  ' + r"\middlehline")
        # lines.append('  ' + table_rule)
        lines[-1] += r" [1ex]"

    # Table rows
    for i, body in enumerate(bodies):
        if i > 0:
            _add_table_rule(lines)
        for row in body.content:
            row_cells = [stringify_cell(cell) for cell in row.content]
            if all(cell.strip() == "" for cell in row_cells) or all(cell == "-" for cell in row_cells) or all(cell == "---" for cell in row_cells):
                _add_table_rule(lines)
            else:
                lines.append('  ' + ' & '.join(row_cells) + r' \\')

    lines.append('  ' + r"\bottomhline")


    # 3. Assemble the LaTeX table
    latex = '\n'.join([
        r'\begin{table}[t]',
        rf'\caption{{{caption_text}}}',
        rf'\label{{{label}}}',
        rf'\begin{{tabular}}{{{col_spec}}}',
        *lines,
        r'\end{tabular}',
        r'\belowtable{}',
        r'\end{table}'
    ])

    return pf.RawBlock(latex, format='latex')

def main(doc=None):
    return pf.run_filter(table_to_latex, doc=doc)

if __name__ == "__main__":
    main()
