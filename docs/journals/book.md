# book

**Template name:** `book`
**Class file:** Standard `book` class (no third-party file)
**Citation style:** natbib `plainnat` (default) or biblatex/biber (per-chapter mode)
**Document structure:** `\frontmatter` / `\mainmatter` / `\backmatter`

## Covers

- Theses and dissertations
- Monographs and book-length technical documents
- Any multi-chapter document where `\include`/`\includeonly` selective
  recompilation is useful

## YAML setup

```yaml
journal:
    template: book
    # options: 11pt,a4paper,openright   # default; override as needed
bibliography: references.bib
```

## Front-matter content

The `book` template emits a `\frontmatter` block between `\maketitle`
and `\mainmatter`. Populate it via YAML keys or matching `# ...`
markdown sections (YAML wins on conflict):

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
body, or declare chapters via YAML:

```yaml
chapters:
  - chapters/intro.md
  - chapters/methods.md
  - chapters/results.md
```

Top-level embeds compile to `\include{stem}` for the `book` template.
See [docs/multi-file.md](../multi-file.md) for the full embed reference.

## Selective recompilation

```
texmark thesis.md --only chapters/methods.md
```

Injects `\includeonly{methods}` into the preamble — only that chapter is
typeset this pass while LaTeX still reads all other chapters' `.aux`
files for cross-references.

## Per-chapter bibliographies (biblatex)

```yaml
bibliography_per_chapter: true
```

Swaps natbib for biblatex/biber and wraps each chapter in a
`refsection` so each chapter prints its own References section. See
[docs/multi-file.md](../multi-file.md) for the full reference.

## Custom preamble

```yaml
preamble: macros.tex   # or inline block scalar; see docs/preamble.md
```

## Recognised section headings

- `# Abstract`
- `# Preface`
- `# Foreword`
- `# Acknowledgments`
