# classicthesis

**Template name:** `classicthesis`
**Class file:** KOMA-Script `scrreprt` + bundled `classicthesis.sty`
**Citation style:** natbib `plainnat` (default) or biblatex/biber (per-chapter mode)
**Document structure:** No `\frontmatter`/`\mainmatter`/`\backmatter` (`scrreprt` lacks them)
**License note:** `classicthesis.sty` is bundled under `texmark/templates/classicthesis/`
and is **GPL-licensed** (by André Miede). See the `NOTICE` file alongside it.
texmark itself is MIT-licensed; the bundled package is redistributed under its
own license.

## Covers

- PhD and master's theses — classicthesis is the most-cited thesis
  template in the LaTeX community (Bringhurst-inspired typography,
  chapter headers in small-caps and oldstyle figures)
- Any document where you want classicthesis's elegant, readable style

## YAML setup

```yaml
journal:
    template: classicthesis
    # options: twoside,openright,titlepage,numbers=noenddot,headinclude,a4paper,11pt,BCOR=5mm,DIV=12
    #            ^ these are the defaults; override the full string if needed
bibliography: references.bib
```

## classicthesis package options

The classicthesis package itself accepts options that control
micro-typographic details (chapter number style, margin notes, etc.).
Pass them via a YAML key:

```yaml
classicthesis-options: "drafting,eulerchapternumbers,parts"
```

When absent, the package is loaded with its own defaults
(`\usepackage{classicthesis}`). When set, the value is passed verbatim:
`\usepackage[drafting,eulerchapternumbers,parts]{classicthesis}`.

The `classicthesis-options:` key uses a hyphen, which Jinja2 cannot
reference directly. texmark surfaces it as `classicthesis_options`
automatically.

## Front-matter content

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

Top-level embeds compile to `\include{stem}` for the `classicthesis`
template. See [docs/multi-file.md](../multi-file.md) for the embed
reference.

## Selective recompilation

```
texmark thesis.md --only chapters/methods.md
```

## Per-chapter bibliographies (biblatex)

```yaml
bibliography_per_chapter: true
```

See [docs/multi-file.md](../multi-file.md).

## Custom preamble

```yaml
preamble: macros.tex   # or inline block scalar; see docs/preamble.md
```

## Recognised section headings

- `# Abstract`
- `# Preface`
- `# Foreword`
- `# Acknowledgments`
