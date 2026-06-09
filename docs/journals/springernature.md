# Springer Nature — Nature, Nature Communications, Nature Climate Change, …

**Template name:** `springernature`
**Aliases:** `springer`, `nature`, `naturecomms`, `natclimchange`, `natgeoscience`, `scirep`
**Class file:** [sn-jnl.cls](https://github.com/perrette/texmark/blob/main/texmark/templates/springernature/sn-jnl.cls) (Springer Nature v2.1, April 2023)
**Citation style:** `\cite{}` numbered (default; per-style selectable)
**Example PDF:** [build/example-springernature.pdf](https://github.com/perrette/texmark/blob/main/build/example-springernature.pdf)

## Covers

A single class for the full Springer Nature catalog:

- **Nature Portfolio:** Nature, Nature Communications, Nature Geoscience,
  Nature Climate Change, Nature Methods, Nature Physics, Nature Materials,
  Nature Genetics, …
- Scientific Reports
- Generic Springer journals (Climatic Change, …)
- BMC journals

The journal-specific aliases (`naturecomms`, `natclimchange`, …) all resolve
to the same template — the journal is selected at submission, not in LaTeX.

## YAML setup

```yaml
journal:
    template: nature           # or springer, naturecomms, natclimchange, scirep, ...
    options: [sn-nature, pdflatex, iicol]      # default — Nature, 2-column
    # options: [sn-nature, pdflatex]           # Nature, single-column
    # options: [sn-basic, pdflatex]            # generic Springer numbered style
    # options: [sn-vancouver, Numbered, pdflatex]
    # options: [sn-apa, pdflatex]              # APA author-year (then disable force_cite — see below)
    # options: [sn-chicago, pdflatex]
    # options: [referee, sn-nature, pdflatex]  # double-spaced for review
```

### Reference style options (the first option group)

| option | description | citation marker |
| --- | --- | --- |
| `sn-nature` | Nature Portfolio numbered style | `\cite{}` |
| `sn-basic` | Generic Springer / Chemistry | `\cite{}` (numbered or namedate) |
| `sn-mathphys` | Math & Physical Sciences | `\cite{}` (numbered or namedate) |
| `sn-aps` | American Physical Society | `\cite{}` |
| `sn-vancouver` | Vancouver-style references | `\cite{}` |
| `sn-chicago` | Chicago / Humanities | `\cite{}` |
| `sn-apa` | APA author-year | `\citep{}` / `\citet{}` |

Add `Numbered` (e.g. `[sn-vancouver, Numbered, pdflatex]`) where supported
to switch a namedate-style to its numbered variant.

### Other options

- `pdflatex` — use pdflatex (default; otherwise xelatex)
- `referee` — double-spaced submission style
- `lineno` — print line numbers in the margin
- `iicol` — two-column layout (default in the template)

## Recognised section headings

- `# Abstract`
- `# Keywords`
- `# Acknowledgements`
- `# Funding`
- `# Ethics Approval`
- `# Data Availability`
- `# Author Contributions`
- `# Competing Interests`
- `# Appendix`

Declarations are gathered under a single `\section*{Declarations}` block
with `\paragraph*` sub-headings — the layout Nature expects.

## Citation handling

The default `force_cite` filter rewrites all pandoc-emitted citations to
plain `\cite{}` which matches every numbered style.

If you select `sn-apa` (author-year), disable the filter so `\citet` and
`\citep` are preserved:

```yaml
filters: []      # at the top level of the yaml header
```

## Bundled bibliography styles

Each reference style has a matching `.bst` file in the template directory:
`sn-nature.bst`, `sn-basic.bst`, `sn-mathphys.bst`, `sn-aps.bst`,
`sn-vancouver.bst`, `sn-chicago.bst`, `sn-apacite.bst`. The class picks
the right one automatically from the documentclass option.
