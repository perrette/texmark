# Figures

An image written as `![caption](path)` becomes a LaTeX `figure` environment with
the caption attached and a label assigned.

## Labelling and referencing

Give a figure a label with a `{#fig:…}` attribute on the image:

```markdown
![Global SAT vs SST anomaly](images/sat-vs-sst.png){#fig:sat-vs-sst}
```

If you omit the attribute, texmark auto-labels the figure from the image
filename stem — `images/eof.png` becomes `fig:eof`.

Reference it with `@fig:sat-vs-sst` or `[#](#fig:sat-vs-sst)` (texmark emits a
bare `\ref`, so write the word "Figure" yourself). See
[Cross-references](cross-reference.md) for the two forms and when to use each.

## Width and spanning

| Keyword | Default | Effect |
|---|---|---|
| `figure-width` | `100%` | image width; percent is a fraction of `\linewidth` |
| `figure-span` | `column` | `full` spans both columns (a `figure*` float) |

Both can be set globally in the YAML front-matter or per-figure in the image
attributes; the per-figure value wins:

```yaml
figure-width: 80%
figure-span: full
```

```markdown
![cap](img.png){width=60%}
![cap](img.png){figure-span=full}
```

## Collecting figures at the end

To float every figure and table to the end of the document (as some journals
require), add to the front-matter:

```yaml
collect_figures_and_tables: true
```

## Figure paths

texmark resolves `![](path)` URLs by GitHub's rules: **no leading slash** is
relative to the markdown file's directory; a **leading slash** is relative to
the project root (detected via `git rev-parse --show-toplevel`, or the CWD for
non-git projects, or an explicit `--project-root <path>` / `project_root:` in the
front-matter). A URL that resolves to no existing file is left unchanged and
logged as a warning — check the build output if a figure comes out missing.

Once resolved, each URL is rewritten in the `.tex` relative to the build
directory; the files stay where they are on disk. Two flags change that:

- `--figure-folders <dir> …` (yaml `figure_folders:`) feeds LaTeX's
  `\graphicspath` so figures under those folders get short URLs in the `.tex`
  (first match wins). Ignored when `--copy-figures` is set.
- `--copy-figures` (yaml `copy_figures: true`) bundles every referenced figure
  flat into `<build>/figures/` for a self-contained build. Basenames are kept
  when unique, disambiguated with a content-hash suffix on collision, and
  deduplicated when the same file is referenced twice. A `.texmark-figures`
  manifest records what texmark wrote so the next build cleans only its own
  files.

Remote (`http(s)://`) URLs are always downloaded into
`<build>/figures/<hash>/<basename>`, regardless of these flags.

## PNGs that pdflatex decodes

pdflatex copies the compressed data of a PNG into the PDF as it is, unless the
PNG has an alpha channel, more than 8 bits per sample, or interlacing: such a
PNG is decoded and compressed again on every pass (about 0.5 s per pass for a
large screenshot). When [Pillow](https://pypi.org/project/pillow/) is
installed, texmark replaces these PNGs by a converted copy when the conversion
loses nothing:

- an alpha channel that is 255 everywhere (screenshots, most plots saved with
  `matplotlib`) is dropped;
- an interlaced PNG is written without interlacing.

PNGs with real transparency and 16-bit PNGs are used as they are. The
converted copies are kept in `<build>/.texmark-cache/figures/<hash>/`, keyed by
the contents of the original, which is never modified. With `--copy-figures`,
the converted copy is the one bundled in `<build>/figures/`, under the
original name. Without Pillow, texmark prints a warning for each such PNG.
