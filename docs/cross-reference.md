# Cross-references

How to reference a labelled equation, figure, table, or section from elsewhere
in the same document. Labels themselves are defined in the
[Equations](equations.md), [Figures](figures.md), and [Tables](tables.md)
pages; this page covers only how to point at them. References *between* separate
companion files are covered in [Multi-file projects](multi-file.md).

## Two forms

texmark accepts two syntaxes for a same-document reference:

| Source | PDF | Markdown preview / GitHub |
|---|---|---|
| `@eq:foo` | the number | literal text `@eq:foo` |
| `[#](#eq:foo)` | the number | clickable `#` that jumps to the target |

- `@id` is the pandoc convention — terse, but shows as literal text in the
  preview and on GitHub.
- `[#](#id)` is an ordinary markdown link, so it stays a clickable jump in the
  preview and on GitHub. The `#` link text is what keeps it visible; an empty
  `[](#id)` also resolves to the number but renders as nothing in the preview.

Use `@id` if you want terse, pandoc-portable source; use `[#](#id)` if a working
link in the Markdown preview matters. Both produce the same reference in the PDF.

## Which command each prefix produces

The prefix on the label selects the LaTeX command:

| Prefix | Command | PDF renders as |
|---|---|---|
| `eq:` | `\eqref` | a parenthesised number — "(3)" |
| `fig:` | `\ref` | a bare number — "3" |
| `tbl:` | `\ref` | a bare number — "3" |
| `sec:` | `\ref` | a bare number — "3" |
| `lst:` | `\ref` | a bare number — "3" |

`\eqref` supplies its own parentheses; `\ref` does not add any word. Write the
noun yourself: `Figure @fig:eof` → "Figure 3", `Table [#](#tbl:gulf)` → "Table 2".
The number is computed by LaTeX's two-pass `.aux` resolution, so it appears only
in the PDF, never in the preview. There is no range syntax — write both ends:
`\eqref{eq:a}–\eqref{eq:b}`.

## Several references in one bracket

When every key in a bracket has one of these prefixes, the references are
joined with commas and "and":

| Source | LaTeX |
|---|---|
| `[@fig:a; @fig:b]` | `\ref{fig:a} and~\ref{fig:b}` |
| `[@fig:a; @fig:b; @fig:c]` | `\ref{fig:a}, \ref{fig:b} and~\ref{fig:c}` |
| `[@eq:a; @eq:b]` | `\eqref{eq:a} and~\eqref{eq:b}` |
| `[@fig:a; @tbl:t]` | `\ref{fig:a} and~\ref{tbl:t}` |

Text written in the bracket before the first key or after the last one is kept:
`[see @fig:a; @fig:b, left]` → `see \ref{fig:a} and~\ref{fig:b}, left`. As for a
single reference, write the noun yourself: `Figures [@fig:a; @fig:b]` →
"Figures 1 and 2". A bracket that also holds a real citation key
(`[@fig:a; @smith2020]`) is left as a citation.

## The two forms are not symmetric

- `[#](#id)` works for **any** label. Unknown prefixes fall back to `\ref`, so a
  heading slug like `[#](#my-heading)` resolves even though it has no `…:` prefix.
- `@id` works **only** for the five prefixes above (`eq:`, `fig:`, `tbl:`,
  `sec:`, `lst:`). An `@` with any other prefix is treated as a bibliography citation,
  not a reference — e.g. `@my-heading` becomes a citation, and `@tab:gulf` (note
  `tab`, not `tbl`) does too. When in doubt, `[#](#id)` is the safe form.

These are the same prefixes used by
[pandoc-crossref](https://github.com/lierdakil/pandoc-crossref), so `tbl:` (not
`tab:`) is the table prefix.

## Words instead of a number

A link whose text is anything other than empty or `#` is left for pandoc and
becomes a `\hyperref` — a clickable link carrying those words rather than a
number:

```markdown
see [the prior](#eq:prior)   →   \hyperref[eq:prior]{the prior}
```

Use that when you want words; use `#` or `@id` when you want the number.

## Headings

Headings are labelled automatically from their slug, with no `{#…}` attribute:
`# My Heading` can be referenced as `[#](#my-heading)`. To reference a heading
with `@sec:…`, give it an explicit label instead — `# My Heading {#sec:intro}`,
referenced as `@sec:intro`.
