# Build backends and engines

texmark separates the **driver** (what orchestrates LaTeX passes and bibtex)
from the **engine** (the actual TeX program). Both have sensible defaults and
both are configurable from the CLI or YAML.

| `--backend` | What it does | Honors `--engine`? |
| --- | --- | --- |
| `latexmk` *(default)* | Reads `.aux`/`.fls`/`.bbl` between passes and reruns *only* what's stale. Drives bibtex automatically. Typically **2–3× faster** on incremental edits than the old fixed 3-pass sequence. | yes |
| `raw` | Runs `engine → bibtex → engine → engine` unconditionally — the original behaviour. Use when latexmk isn't available. | yes |
| `tectonic` | Standalone Rust rewrite of the TeX stack: engine + driver + bibtex-equivalent in one binary. Auto-fetches missing packages on first run. | no — uses its own XeTeX-derived engine |

`--engine` selects the TeX program when the backend honors it:

- `pdflatex` *(default)* — broadest package compatibility, fastest cold start.
- `xelatex` — native Unicode + system OpenType fonts (`fontspec`).
- `lualatex` — LuaTeX scripting + modern fontspec.

YAML frontmatter equivalents:

```yaml
backend: latexmk          # or raw, tectonic
engine: pdflatex          # or xelatex, lualatex
```

CLI flags win over YAML.

> **Unicode and HTML in bibliographies / body text** — texmark transparently
> rewrites non-ASCII Unicode and CrossRef-style HTML markup
> (`<i>δ</i><sup>18</sup>O`) into LaTeX commands at build time, so pdflatex
> doesn't silently drop scientific characters from your references. Default
> behaviour is engine-aware (`--rewrite-unicode auto`): on for pdflatex,
> off for lualatex/xelatex; pass `on`/`off` to override. See
> [the encoding strategy page](encoding.md) for the full strategy, performance
> numbers, and how the engine choice affects it.
