import panflute as pf
from texmark.logs import logger

def stringify_cell(cell):
    latex = pf.convert_text(
        cell.content,
        input_format='panflute',
        output_format='latex',
    )
    return latex

def table_to_latex(elem, doc):

    table_type = doc.get_metadata('table_type') or doc.get_metadata('journal').get("template")

    if not isinstance(elem, pf.Table):
        return

    # Safely extract caption
    if elem.caption:
        caption_text = stringify_cell(elem.caption)

    label_ = elem.identifier
    label = f"tab:{label_}" if label_ else ""

    # 2. Extract header and rows
    headers = elem.head.content
    bodies = elem.content
    ncols = len(headers[0].content)

    col_spec = 'l' * ncols
    lines = [r"\\"] if table_type == "science" else []
    lines.append('  ' + r"\tophline" if table_type == "copernicus" else '  ' + r"\hline")
    # Table header
    header_cells = ["\n".join([stringify_cell(line) for line in lines]) for lines in zip(*[h.content for h in headers])]
    lines.append('  ' + ' & '.join(header_cells) + r' \\')
    lines.append('  ' + r"\middlehline" if table_type == "copernicus" else '  ' + r"\hline")

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

    lines.append('  ' + r"\bottomhline" if table_type == "copernicus" else '  ' + r"\hline")


    # 3. Assemble the LaTeX table
    latex = '\n'.join([
        r'\begin{table}[t]',
        r'\centering',
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
