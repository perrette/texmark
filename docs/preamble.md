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

1. `{{ xr_preamble }}` — xr-hyper `\externaldocument` declarations (from companions)
2. `{{ user_preamble }}` — your `preamble:` content
3. `\begin{document}`

xr-hyper is loaded before user-defined macros so any user command that
references companion labels compiles correctly.

## Default

When `preamble:` is absent, nothing is emitted and single-file builds
are byte-identical to before.
