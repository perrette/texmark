# AGU — JGR family, GRL, Earth's Future, JAMES, …

**Template name:** `agujournal`
**Aliases:** `agu`, `jgr`, `grl`, `james`, `earthsfuture`, `wrr`, `rog`
**Class file:** [agujournal2019.cls](../../texmark/templates/agujournal/agujournal2019.cls) (AGU / Wiley, Jan 2019)
**Citation style:** apacite (author-year)
**Example PDF:** [build/example-agujournal.pdf](../../build/example-agujournal.pdf)

## Covers

| journal | alias |
| --- | --- |
| Journal of Geophysical Research (Atmospheres / Oceans / Earth Surface / Solid Earth / Planets / Space Physics / Biogeosciences) | `jgr` |
| Geophysical Research Letters | `grl` |
| Earth's Future | `earthsfuture` |
| Journal of Advances in Modeling Earth Systems | `james` |
| Water Resources Research | `wrr` |
| Reviews of Geophysics | `rog` |
| (and every other AGU journal — same class) | `agujournal` / `agu` |

The newer `agujournal2025.cls` is **not** used here. The 2025 version
requires xelatex/lualatex plus system fonts (fontspec, unicode-math),
which would break the texmark pdflatex pipeline. Use the 2019 class for
submission; AGU production handles typesetting separately.

## YAML setup

```yaml
journal:
    template: agujournal
    options: final         # default — production look
    # options: draft       # 1.5× line-spaced submission style
    name: "Geophysical Research Letters"    # optional, sets \journalname{...}
```

## AGU-specific sections

- `# Key Points` — exactly 3 items, each ≤140 characters, no special
  punctuation. Rendered into `\begin{keypoints}`.
- `# Plain Language Summary` — short general-audience summary, rendered
  inside `\begin{abstract}` as a `\begin{plainlanguagesummary}` block.

Plus the usual:

- `# Abstract`
- `# Acknowledgments` — also receives the contents of `# Data Availability`
  as `\textbf{Data availability statement.}` (AGU style)
- `# Appendix` / `# Supplementary Information`

## Citation handling

`agujournal2019.cls` uses the **apacite** package, not natbib. That means
`\cite{key}` is parenthetical "(Author, year)" and `\citeA{key}` is in-text
"Author (year)" — opposite of natbib.

texmark ships an `apacite_cite` filter that rewrites pandoc's natbib
output for you:

| pandoc | natbib | apacite (output) |
| --- | --- | --- |
| `@key` (in-text) | `\citet{key}` | `\citeA{key}` |
| `[@key]` (parens) | `\citep{key}` | `\cite{key}` |

So your markdown citations work without any change.

## Gotchas

- The class loads `apacite`, `hyperref`, `graphicx`, `xcolor`, `url`,
  `trackchanges`, `lineno`, `indentfirst`, `ragged2e`, `rotating`, `ulem`.
  The template adds `amsmath`/`amssymb` for `\begin{align}` etc.
- `trackchanges.sty` ships with the template directory (it's not on
  TeXLive by default).
