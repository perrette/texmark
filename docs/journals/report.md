# report

**Template name:** `report`
**Class file:** Standard `report` class (no third-party file)
**Citation style:** natbib `plainnat` (default) or biblatex/biber (per-chapter mode)
**Document structure:** No `\frontmatter`/`\mainmatter`/`\backmatter` (the `report` class lacks them)

## Covers

- Technical reports
- Master's theses and shorter dissertations
- Multi-chapter documents that do not need the two-sided book structure

## YAML setup

```yaml
journal:
    template: report
    # options: 11pt,a4paper   # default; override as needed
bibliography: references.bib
```

## Front-matter content

Unlike the `book` template, the `report` class has no preliminary-matter
commands (`\frontmatter` etc.). The template still supports:

| YAML key | Markdown heading | Emitted as |
|---|---|---|
| `dedication: "..."` | *(YAML only)* | Centered italic dedication page |
| `preface: "..."` | `# Preface` | `\chapter*{Preface}` |
| `foreword: "..."` | `# Foreword` | `\chapter*{Foreword}` |
| `abstract: "..."` | `# Abstract` | `\begin{abstract}...\end{abstract}` |
| `list_of_figures: true` | *(YAML only)* | `\listoffigures` |
| `list_of_tables: true` | *(YAML only)* | `\listoftables` |

A `\tableofcontents` is always emitted.

## Multi-chapter layout

Use `![](chapter.md)` or `[Chapter title](chapter.md){.include}` in the
body, or declare chapters via the `chapters:` YAML key. Top-level embeds
compile to `\include{stem}`. See [docs/multi-file.md](../multi-file.md).

## Selective recompilation

```
texmark report.md --only chapters/methods.md
```

Injects `\includeonly{methods}` — only that chapter is typeset this
pass.

## Per-chapter bibliographies (biblatex)

```yaml
bibliography_per_chapter: true
```

See [docs/multi-file.md](../multi-file.md) for the full reference.

## Custom preamble

```yaml
preamble: macros.tex   # or inline block scalar; see docs/preamble.md
```

## Recognised section headings

- `# Abstract`
- `# Preface`
- `# Foreword`
- `# Acknowledgments`
