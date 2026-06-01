# Beamer presentations

**Template name:** `beamer`
**Aliases:** `slides`, `presentation`
**Class file:** `beamer` (standard LaTeX class, no third-party file required)
**Citation style:** natbib `plainnat`

## Covers

- Lecture slides, conference presentations, seminar talks.
- Any content where a sequence of frames (slides) is more appropriate than a
  flat article body.

The body of the document is compiled with pandoc's `-t beamer` writer, which
turns heading-delimited sections into `\begin{frame}…\end{frame}` blocks.
The Jinja2 outer template owns only the document scaffolding — class options,
theme, title metadata, and the optional title and bibliography frames.

## YAML setup

```yaml
journal:
    template: beamer

beamer:
    theme: default          # any installed Beamer theme; default: "default"
    colortheme: seahorse    # optional colour theme
    fonttheme: serif        # optional font theme
    aspectratio: 169        # optional: 169 | 1610 | 149 | 54 | 43 | 32
    slide_level: 2          # heading level that becomes a frame (default: 2)
```

At minimum, only `journal.template: beamer` is required; all `beamer:` keys
are optional.

## Preamble loaded

```
amsmath, amssymb, amsfonts, bm
graphicx / booktabs
natbib
```

Additional packages can be declared via `metadata.packages` in the frontmatter
(duplicates of the above are silently skipped).

## Frame syntax

With the default `slide_level: 2`, level-2 headings (`## Frame title`) become
individual frames:

```markdown
# Section title

## First frame

Content of the first slide.

## Second frame

More content.
```

Setting `beamer.slide_level: 1` promotes level-1 headings to frames instead.

## Recognised YAML keys (`beamer:` block)

| Key | Default | Effect |
|-----|---------|--------|
| `theme` | `default` | `\usetheme{…}` |
| `colortheme` | *(none)* | `\usecolortheme{…}` |
| `fonttheme` | *(none)* | `\usefonttheme{…}` |
| `aspectratio` | *(none)* | `\documentclass[aspectratio=…]{beamer}` |
| `slide_level` | `2` | `--slide-level=N` passed to pandoc |

## Title and bibliography

A title frame (`\titlepage`) is inserted automatically when `title:` is
present in the frontmatter.  A bibliography frame is inserted automatically
when `bibliography:` is present.  Authors map to `\author{…}` and
affiliations to `\institute{…}`.

## Limitations (v1)

- **Overlays / pauses** — `\pause`, `\only<>`, `\uncover<>` etc. are not
  specially supported; use raw LaTeX if needed.
- **Posters** — out of scope; use a dedicated poster class.
- **Per-frame options** — custom frame options (fragile, shrink, …) require
  raw LaTeX fenced divs; no YAML shorthand is provided.
