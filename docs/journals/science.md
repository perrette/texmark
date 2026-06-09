# AAAS Science

**Template name:** `science`
**Class file:** Standard `article` class with the [scicite.sty](https://github.com/perrette/texmark/blob/main/texmark/templates/science/scicite.sty) Science citation style
**Citation style:** `\cite{}` (numbered)
**Example PDF:** [build/example-science.pdf](https://github.com/perrette/texmark/blob/main/build/example-science.pdf)

## Covers

- Science
- Science Advances
- Science Translational Medicine
- Science Signaling
- Science Immunology
- Science Robotics

(All AAAS journals share the same LaTeX format.)

## YAML setup

```yaml
journal:
    template: science
```

No `journal.options` are accepted — Science fixes the layout (12pt,
1in margins, double-spaced).

## Citation handling

A built-in `force_cite` filter rewrites pandoc's natbib-style
`\citet{key}` / `\citep{key}` to plain `\cite{key}`. Science uses numbered
references throughout the body and references list, so all citations end
up identical regardless of how you wrote them in markdown.

## Recognised section headings

- `# Abstract`
- `# Acknowledgements`
- `# Materials and Methods` / `# Methods` / `# Methodology`
- `# Supplementary Material` / `# Supplementary Information`
- `# Appendix`
- `# Author Contributions`
- `# Competing Interests`

`# Materials and Methods` is rendered into the Science supplement back-matter.

Heading levels in the body are rewritten to `\paragraph*{...}` so the
output matches Science's flat heading style.
