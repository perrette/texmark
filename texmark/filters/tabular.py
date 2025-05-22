import panflute as pf

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
    body = elem.content[0]
    rows = body.content
    ncols = len(headers[0].content)

    def stringify_cell(cell):
        return pf.stringify(cell).replace('\n', ' ')

    col_spec = 'l' * ncols
    lines = ['  ' + r"\tophline"]
    # Table header
    header_cells = ["\n".join([stringify_cell(line) for line in lines]) for lines in zip(*[h.content for h in headers])]
    lines.append('  ' + ' & '.join(header_cells) + r' \\')
    lines.append('  ' + r"\middlehline")

    # Table rows
    for row in rows:
        row_cells = [stringify_cell(cell) for cell in row.content]
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
