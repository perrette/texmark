# Multi-file projects

texmark can compile a manuscript split across multiple markdown files,
and supports a **main paper + supplementary information** pair with
validated cross-references between the two documents.

## Embed syntax — splitting a manuscript into chapters

Two equivalent syntaxes declare that a markdown file should be included
in the compiled document:

### Image-style (original form)

```markdown
![](chapters/introduction.md)
```

This is the canonical embed declaration. In GitHub's markdown renderer
it displays as a broken image (the `.md` URL has no image to show), but
it compiles correctly.

### Link-style with `.include` class (GitHub-clean alternative)

```markdown
[Introduction](chapters/introduction.md){.include}
```

GitHub renders this as a plain link (the `{.include}` attribute is
invisible in the rendered view). The class match is exact — `includes`
or `included` do not trigger embedding.

Both forms are equivalent and produce identical LaTeX output.

**Plain markdown links to `.md` files without `{.include}` are
untouched.** Only links carrying the exact `include` class are rewritten.

## What gets emitted

The embed filter rewrites each recognized embed node:

| Template family | Embed at top level | Nested embed |
|---|---|---|
| article-class (`arxiv`, `elsarticle`, etc.) | `\input{stem}` | `\input{stem}` |
| book-family (`book`, `report`, `memoir`, `classicthesis`) | `\include{stem}` | `\input{stem}` |

LaTeX forbids nested `\include`, so embeds inside an already-embedded
file always use `\input` regardless of template class.

## `chapters:` YAML key — alternative discovery

Instead of (or in addition to) embedding files in the markdown body, you
can declare the chapter set in the YAML front-matter of the root file:

```yaml
chapters:
  - chapters/introduction.md
  - chapters/methods.md
  - chapters/results.md
```

Body-discovered embeds and `chapters:` entries are merged into a single
ordered list: body-discovered files first (in body order), then
`chapters:` entries not already present (in YAML order). Duplicates are
removed keeping first occurrence.

## `--only` flag — selective recompilation

For book-family templates, pass one or more chapter stems to compile
only those chapters this pass:

```
texmark thesis.md --only chapters/methods.md
texmark thesis.md --only chapters/methods.md,chapters/results.md
```

This injects `\includeonly{methods,results}` into the master preamble.
All chapter `.aux` files from previous builds are preserved (LaTeX still
reads them for cross-references), but only the listed chapters are
typeset — useful when editing a single chapter in a large thesis.

`--only` is a no-op outside book-family templates (a warning is emitted
and the flag is ignored).

## Build pipeline for embeds

When embedded files are present:

1. Each embedded file is pandoc-compiled to a body-only `.tex` (no
   preamble, no `\begin{document}`) and written to `<build>/<stem>.tex`.
2. The root file is compiled with the master template, which emits
   `\include{stem}` or `\input{stem}` directives pointing at the
   body-only files.
3. `compile_pdf` is called once, on the master `.tex`. The body-only
   files are inputs to LaTeX, not separate compile targets — LaTeX
   concatenates them at compile time, so all labels and references
   resolve natively within one document.

## Companions — main paper + supplementary information

Companions are separate documents that compile to separate PDFs, with
cross-document references between them. Declare companions in the root
file's YAML:

```yaml
companions:
  - si.md
```

The companion file is its own first-class document with its own
front-matter (template, bibliography, etc.). Companions are **not**
embeds — they are never `\input`-ed or `\include`-ed into the root.

### Cross-document links

Use standard markdown links with a `#label` anchor to reference a label
in another document:

```markdown
As shown in [Fig.~S1](si.md#fig:noise), the signal is clear.
```

texmark rewrites this to `\ref{si:fig:noise}` using xr-hyper's
`\externaldocument[si:]{si}` machinery. The mapping uses the companion
file's stem as the prefix.

Links to `.md` files **without** `#anchor` are left as plain hyperlinks.
Links to `.pdf` files (with or without anchor) are also left untouched —
hyperref handles external PDF links.

### Cross-reference distinction

| Syntax | What it does |
|---|---|
| `[text](other.md#label)` | Validated LaTeX cross-ref via xr-hyper (`\ref{other:label}`) |
| `[text](other.pdf)` | External hyperlink via hyperref (NOT a cross-ref) |
| `[text](other.md)` | Plain link (untouched — NOT an embed, NOT a cross-ref) |
| `[text](other.md){.include}` | Embed directive (`\include{other}` or `\input{other}`) |

### `prefix:` and per-counter overrides

Give a companion document independent figure/table numbering (e.g. S1,
S2, …) by declaring a `prefix:` in its own YAML:

```yaml
# si.md front-matter
prefix: S
```

This injects `\renewcommand{\thefigure}{S\arabic{figure}}` (and
equivalents for table, equation, section) into the companion's preamble.

Override a single counter while keeping the umbrella prefix for others:

```yaml
prefix: S
equation-prefix: SE
```

Available per-counter keys: `figure-prefix`, `table-prefix`,
`equation-prefix`, `section-prefix`. A per-counter key overrides
`prefix:` for that counter only.

### Multi-pass build loop

When companions are present, texmark loops the compile cycle until every
document's `.aux` file is byte-identical to the previous pass — xr-hyper
needs at least two passes to resolve cross-document references. The loop
caps at 4 passes; a warning is logged if convergence is not reached.

Single-input invocations and multi-file-without-companions builds remain
single-pass.

## Watch mode

`--watch` tracks all files that affect the build output:

- The root markdown
- Every embedded chapter
- Every companion
- Each companion's bibliography and template (if declared)
- Root bibliography and template

Any modification to any tracked file triggers a full rebuild.

## Project root

Leading-slash figure URLs (`![](/images/fig.png)`) resolve against the
**project root** — a single value shared by all embedded chapters and
companions. Resolution precedence:

1. `--project-root <path>` CLI flag
2. `project_root:` key in the root YAML (path relative to root file's directory)
3. `git rev-parse --show-toplevel` from the root file's directory
4. Fallback: the current working directory (also used when git is not
   installed or refuses to run, e.g. in a container)

All embedded chapters and companions share the same project root, so
`![](/images/fig.png)` in any chapter always resolves to the same file.

## Example project layout

```
thesis/
├── thesis.md          # root: declares chapters: and companions:
├── si.md              # companion with its own template + bibliography
├── chapters/
│   ├── intro.md
│   ├── methods.md
│   └── results.md
├── references.bib
└── images/
    └── fig1.png
```

Root `thesis.md` front-matter:

```yaml
title: "My Thesis"
journal:
  template: book
bibliography: references.bib
chapters:
  - chapters/intro.md
  - chapters/methods.md
  - chapters/results.md
companions:
  - si.md
```

Build:

```
texmark thesis.md --pdf
texmark thesis.md --pdf --only chapters/methods.md   # quick chapter edit
```
