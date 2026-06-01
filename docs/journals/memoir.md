# memoir

**Template name:** `memoir`
**Class file:** Standard `memoir` class (no third-party file)
**Citation style:** natbib `plainnat` (default) or biblatex/biber (per-chapter mode)
**Document structure:** `\frontmatter` / `\mainmatter` / `\backmatter`

## Covers

- Theses and dissertations — memoir's rich chapter-style system gives
  fine-grained control over heading typography
- Book-length documents where you want memoir's built-in page layout
  management (memoir handles geometry itself; no `geometry` package
  conflict)

## YAML setup

```yaml
journal:
    template: memoir
    # options: 11pt,a4paper,openright   # default; override as needed
bibliography: references.bib
```

## Chapter style

memoir has an extensive catalogue of predefined chapter heading styles
(see the memoir manual, chapter 6). Set the style via a YAML key:

```yaml
chapter-style: veelo     # or bringhurst, dash, demo2, pedersen, ...
```

Defaults to `default` when absent.

The `chapter-style:` key uses a hyphen (standard YAML), which Jinja2
cannot reference directly. texmark surfaces it as the template variable
`chapter_style` automatically.

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

Top-level embeds compile to `\include{stem}` for the `memoir` template.
See [docs/multi-file.md](../multi-file.md) for the embed reference.

## Selective recompilation

```
texmark thesis.md --only chapters/methods.md
```

## Per-chapter bibliographies (biblatex)

```yaml
bibliography_per_chapter: true
```

memoir is compatible with both natbib and biblatex; the template loads
exactly one, avoiding double-load conflicts. See
[docs/multi-file.md](../multi-file.md).

## Custom preamble

```yaml
preamble: macros.tex   # or inline block scalar; see docs/preamble.md
```

## Notes

memoir manages page geometry internally. The `geometry` package is
deliberately **not** loaded (the memoir manual documents an
incompatibility). Use memoir's own layout commands
(`\setlrmarginsandblock`, `\setheaderspaces`, etc.) if you need to
override the default layout — put them in `preamble:`.

## Recognised section headings

- `# Abstract`
- `# Preface`
- `# Foreword`
- `# Acknowledgments`
