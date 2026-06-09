# arXiv / generic preprint

**Template name:** `arxiv`
**Aliases:** `preprint`
**Class file:** Standard `article` class (no third-party file)
**Citation style:** natbib `plainnat`
**Example PDF:** [build/example-arxiv.pdf](https://github.com/perrette/texmark/blob/main/build/example-arxiv.pdf)

## Covers

- arXiv preprints (all subject areas)
- Anywhere you want a clean article-class look without journal trappings:
  technical reports, working papers, before you commit to a target journal.

arXiv imposes no class file — any clean article-class submission is
accepted. This template loads a standard preamble that compiles anywhere
TeXLive is installed.

## YAML setup

```yaml
journal:
    template: arxiv
    # biblio_style: plainnat       # default; override e.g. with unsrtnat
```

No `journal.options`.

## Preamble loaded

```
T1 fontenc / utf8 inputenc / lmodern / microtype
geometry (1in margins) / setspace / authblk
amsmath, amssymb, amsfonts, bm
graphicx / booktabs / caption / subcaption
natbib / url / hyperref (colorlinks=true)
```

## Recognised section headings

- `# Abstract`
- `# Keywords` — rendered as `\textbf{Keywords:} kw1, kw2, …` before the body
- `# Acknowledgments`
- `# Data Availability`
- `# Author Contributions`
- `# Competing Interests`
- `# Appendix` / `# Supplementary Material`
