# Custom preamble (`preamble:` YAML field)

The `preamble:` YAML field injects custom LaTeX — `\newcommand`,
`\DeclareMathOperator`, theorem environments, package configuration —
into the active document's preamble. It works across all templates
uniformly and is independent of multi-file features.

## Forms

### Inline block scalar

```yaml
preamble: |
  \newcommand{\degC}{^\circ\mathrm{C}}
  \newcommand{\pCO}[1]{\ensuremath{p\mathrm{CO}_{2}}}
  \DeclareMathOperator{\std}{std}
```

The text is included verbatim in the LaTeX preamble.

### Single file path

```yaml
preamble: macros.tex
```

The file's contents are read and emitted. The path is resolved relative
to the markdown source file's directory.

### List of file paths

```yaml
preamble:
  - macros.tex
  - theorems.tex
```

The files are concatenated in order with a single newline between them.

### Mixed inline + file

Within a list, any entry that starts with `\` or contains a newline is
treated as inline LaTeX rather than a file path:

```yaml
preamble:
  - macros.tex
  - "\\newcommand{\\degC}{^\\circ\\mathrm{C}}"
```

## Ordering guarantee

Templates emit the preamble in this order:

1. `{{ xr_setup }}` — `\usepackage{xr-hyper}` (with companions) and the
   counter prefixes
2. `{{ user_preamble }}` — your `preamble:` content
3. `{{ endofdump }}` — the end of the part of the preamble that texmark can
   precompile (see [Precompiled preamble](build-backends.md#precompiled-preamble))
4. `{{ xr_externals }}` — the `\externaldocument` declarations (from
   companions), which read the companions' `.aux` files on every run
5. `{{ includeonly }}` (book-family templates) and `\begin{document}`

xr-hyper is loaded before user-defined macros. Custom templates can still
use `{{ xr_preamble }}`, which holds the package, the `\externaldocument`
declarations and the counter prefixes together; without `{{ endofdump }}`
the document is compiled without a precompiled preamble.

## Default

When `preamble:` is absent, nothing is emitted and single-file builds
are byte-identical to before.
