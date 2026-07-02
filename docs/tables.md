# Tables

Tables are written as pandoc pipe tables. texmark converts each table to a
LaTeX `table` environment with the caption and label attached, and renders the
cells through pandoc so inline markup (emphasis, math, citations) works inside
cells.

## Writing a pipe table

A pipe table is a header row, a separator row, and one or more body rows,
columns delimited by `|`:

```markdown
| Names | Values |
| - | - |
| Domain | Ocean |
| Era | Anthropocene |
```

The separator row (`| - | - |`) marks the header. Dashes set the column count;
their length does not need to match the content.

## Caption and label

Attach a caption with a line beginning with `:` placed **immediately below the
table, with no blank line in between**:

```markdown
| Names | Values |
| - | - |
| Domain | Ocean |
| Era | Anthropocene |
:A caption for my table {#tbl:gulf}
```

The `{#tbl:gulf}` trailer sets the table's label. In the generated LaTeX this
becomes `\caption{A caption for my table}` and `\label{tbl:gulf}`.

A blank line between the table and the `:` caption line detaches the caption:
pandoc no longer treats it as the table's caption, and the label is lost.

Inline markup works inside the caption: math (`$...$`), emphasis, and citations
are rendered rather than flattened to plain text.

## Referencing a table

Reference a labelled table with `@tbl:gulf` or `[#](#tbl:gulf)` (both produce
`\ref{tbl:gulf}`, a bare number — write the word "Table" yourself). Note the
prefix is `tbl:`, not `tab:`. See [Cross-references](cross-reference.md) for the
two forms and when to use each.

## Other attributes in the trailer

The same trailer can carry classes and key=value attributes alongside (or
instead of) the identifier, separated by spaces:

```markdown
:A caption for my table {#tbl:gulf .narrow width=50%}
```

`#tbl:gulf` sets the label, `.narrow` adds a class, and `width=50%` sets an
attribute.
