# LaTeX encoding: Unicode and HTML in bibliographies and body text

Most users don't need to know any of this. You write UTF-8, you run texmark,
the PDF renders correctly. This page exists for the cases where it doesn't —
to explain *why* it didn't, and *what knob* fixes it.

## The problem in 60 seconds

pdflatex is a 1990s engine. It reads UTF-8 input fine (since LaTeX 2018-04-01
the kernel handles UTF-8 natively), but its **font stack is 8-bit** — each
font has 256 slots and no slot exists for arbitrary Unicode codepoints. When
inputenc's default mapping table doesn't know how to render a codepoint, you
get:

```
! LaTeX Error: Unicode character δ (U+03B4)
               not set up for use with LaTeX.
```

Under `-interaction=nonstopmode` (which texmark uses), pdflatex doesn't halt
— it **drops the character and continues**. The result is silent data loss:
the rendered PDF says "calibration of 18O" instead of "calibration of δ¹⁸O",
and you don't notice unless you read the reference list carefully.

The most common source of this is bibliographies, because:

- `.bib` files often contain Greek letters in titles (δ¹⁸O), primes in proxy
  names (uk′37), thin spaces around units (30 kyr), CrossRef-style HTML
  markup (`<i>δ</i><sup>18</sup>O`), and accented author names.
- `bibtex` copies field bytes from `.bib` straight into `.bbl` with no
  Unicode handling. So whatever was in the `.bib` ends up in the rendered
  bibliography, unchanged.
- The body text rarely triggers this because pandoc converts the most common
  typographic Unicode (em-dash, smart quotes, ellipsis) and most users write
  the rest as LaTeX commands (`$\delta^{18}$O`).

## What texmark does about it

When you build with `--engine pdflatex` (the default), texmark **rewrites
non-ASCII codepoints to their LaTeX equivalents on the way into the build
directory**. Two staging steps:

1. **Bibliography** — when `.bib` is copied into `build/`, the copy is
   passed through `texmark.unicode_bib.rewrite_text`, which converts each
   non-ASCII character to a LaTeX command (`δ` → `\ensuremath{\delta}`,
   `°` → `{\textdegree}`, `<sup>18</sup>` → `\textsuperscript{18}`, etc.).
2. **Body `.tex`** — the same rewrite runs over the pandoc-generated
   master `.tex` (and any embedded-chapter `.tex` chunks) after `build_tex`
   writes them. Catches the rare case of scientific Unicode written
   directly in markdown body text.

The **source files on disk are never touched**. Only the staged copies in
`build/` are rewritten. You can keep your `.bib` and `.md` as readable
UTF-8.

The rewrite is a **no-op for files that contain no non-ASCII characters**.
The file isn't even rewritten, so `mtime` is preserved and `latexmk`'s
fingerprint cache stays valid for incremental builds.

### What the conversions look like

| Input | Output | Source |
| --- | --- | --- |
| `δ` (U+03B4) | `\ensuremath{\delta}` | pylatexenc |
| `°` (U+00B0) | `{\textdegree}` | pylatexenc |
| `±` (U+00B1) | `\ensuremath{\pm}` | pylatexenc |
| `—` (em-dash) | `{\textemdash}` | pylatexenc |
| `"` `"` (smart quotes) | ` `` ` ` '' ` | pylatexenc |
| `¹` `²` `³` (Latin-1 sup) | `\textsuperscript{1}` `…{2}` `…{3}` | overrides |
| `⁰` `⁴`–`⁹` (Unicode sup) | `\textsuperscript{N}` | overrides |
| `₀`–`₉` (Unicode sub) | `\textsubscript{N}` | overrides |
| `<i>X</i>` | `\textit{X}` | HTML map |
| `<sup>X</sup>` | `\textsuperscript{X}` | HTML map |
| `<sub>X</sub>` | `\textsubscript{X}` | HTML map |
| `<b>X</b>` / `<strong>X</strong>` | `\textbf{X}` | HTML map |
| `<em>X</em>` | `\emph{X}` | HTML map |

Adjacent `\textsuperscript`/`\textsubscript` blocks are then **merged**:
`\textsuperscript{1}\textsuperscript{8}` collapses to
`\textsuperscript{18}`, so an isotope label like `δ¹⁸O` renders as one
typographically coherent piece.

### Real example: a CrossRef-exported entry

Input (`references.bib`):

```bibtex
@article{malevich_vetter2019,
  title = {Global Core Top Calibration of <i>δ</i><sup>18</sup>O in
           Planktic Foraminifera to Sea Surface Temperature},
  ...
}
```

Staged copy (`build/references.bib`):

```bibtex
@article{malevich_vetter2019,
  title = {Global Core Top Calibration of \textit{\ensuremath{\delta}}\textsuperscript{18}O in
           Planktic Foraminifera to Sea Surface Temperature},
  ...
}
```

Rendered in the PDF: *Global Core Top Calibration of δ¹⁸O in Planktic Foraminifera…*

## The optional dependency: `pylatexenc`

The Unicode → LaTeX mapping comes from
[`pylatexenc`](https://pypi.org/project/pylatexenc/), a small pure-Python
package (~250 KB wheel, BSD-licensed) that ships a comprehensive table of
roughly 3000 Unicode codepoints with their LaTeX equivalents. It's listed in
`requirements.txt` and installs automatically with `pip install texmark`.

If `pylatexenc` is **not** installed (for example if you're using texmark
under a constrained sandbox), the staging step degrades gracefully: the
file is copied byte-for-byte and the build behaves exactly as it did before
the encoding feature existed. You can still hit the "Unicode character not
set up" failure mode, but only on chars that the underlying engine doesn't
already handle.

A small in-tree overrides table fills gaps in `pylatexenc`'s coverage that
matter for scientific bibliographies — chiefly Unicode super/subscript
blocks (`U+2074`–`U+2079`, `U+2080`–`U+208E`) that `pylatexenc` doesn't
map.

## Unmapped characters

A few rare codepoints have no clean LaTeX equivalent (private-use blocks,
emoji, exotic mathematical symbols). When the rewriter encounters one, it:

1. Leaves the character **in place** in the staged copy (silently deleting
   it would be worse than the existing pdflatex behavior).
2. Emits a `WARNING` per offender with the file path, line number, and
   surrounding `@entry{key}` so you can hand-fix the entry, e.g.:

```
WARNING /path/refs.bib:117: U+1F4A9 ('💩') in @entry{joke_2024}
has no LaTeX replacement and will be dropped from the PDF under pdflatex.
Fix by editing the .bib entry or switching to engine: lualatex / xelatex.
```

The build continues; the offending char gets dropped from the PDF the same
way it would have without this feature. You only see the warning, which can be used to triage.

## How the engine changes the picture

texmark only runs the body `.tex` rewrite under `engine: pdflatex` (the
default). Under `lualatex` or `xelatex`:

| | pdflatex | lualatex / xelatex |
| --- | --- | --- |
| Reads UTF-8 natively | yes | yes |
| Renders arbitrary UTF-8 directly | **no** (8-bit fonts) | yes (OpenType fonts) |
| `.bib` rewrite | runs (defensive — never hurts) | runs (defensive — never hurts) |
| Body `.tex` rewrite | runs | **skipped** (you may prefer raw codepoints for OpenType shaping) |
| Recommended for: | speed; broadest package compatibility | full Unicode + system fonts |

So the practical knobs are:

```yaml
# Default — fast, 8-bit, texmark normalizes Unicode for you.
engine: pdflatex

# Native UTF-8 rendering; no Unicode rewriting on the body.
engine: lualatex
# or
engine: xelatex
```

CLI overrides:

```sh
texmark sources/main.md --pdf --engine lualatex
```

`pylatexenc` runs on the `.bib` regardless of engine because the LaTeX
commands it emits (`\ensuremath{\delta}`, `\textit{…}`, etc.) are valid in
all three engines — they just become unnecessary work under lualatex /
xelatex.

## How `.bib` formatting affects what you get

### Things that work transparently
- Raw UTF-8 Greek letters, math symbols, primes, degrees, super/subscripts.
- CrossRef-exported entries with inline HTML markup (`<i>`, `<sup>`, `<sub>`,
  `<em>`, `<b>`, `<strong>`).
- Accented author names (é, ñ, ü, ç, etc. — pdflatex handles these via
  inputenc's default Latin-1 table even without our rewrite).

### Things that need attention
- **Private-use codepoints / emoji / very exotic math glyphs.** You'll see
  the warning. Either escape the char in the `.bib` or switch engine.
- **Tags that are not in our HTML map** (e.g. `<custom>`). Left untouched so
  you don't get a surprise rewrite of something you actually meant. If you
  want one converted, add it to `_HTML_TAG_MAP` in
  [texmark/unicode_bib.py](../texmark/unicode_bib.py) (PRs welcome).
- **Already-LaTeX content like `{\'e}`** is ASCII, so the rewriter ignores it.
  Safe to mix LaTeX escapes with raw Unicode in the same `.bib`.

## How main-text formatting affects what you get

Most scientific writing in markdown uses LaTeX-style notation for math
(`$\delta^{18}$O`, `$T_{\mathrm{sst}}$`), which texmark and pandoc pass
through unchanged. The cases where the body rewrite kicks in are:

- You wrote raw Unicode in the markdown (`δ¹⁸O` instead of `$\delta^{18}$O`).
- Pandoc passed it through to the `.tex` (true for all scientific Unicode,
  not just typographic).
- Engine is `pdflatex`.

In that case the rewrite turns your raw `δ¹⁸O` into
`\ensuremath{\delta}\textsuperscript{18}O` in the staged `.tex`. Same visual
result, no "not set up" error.

If you actively prefer raw Unicode in the body (e.g. to take advantage of
OpenType ligatures or kerning under lualatex), set `engine: lualatex` and
the body rewrite is skipped.

## Backend interaction

The encoding work is **upstream** of any backend (`latexmk`, `raw`,
`tectonic`). By the time `latexmk` or `tectonic` sees the staged files,
they're already rewritten. So the backend choice doesn't change what the
encoding layer does — it only changes how the resulting `.tex`/`.bib` get
compiled.

One small interaction worth knowing: when texmark rewrites a `.tex` body
(under pdflatex), it changes the file's bytes, which invalidates `latexmk`'s
fingerprint cache and forces a rebuild on the next pass. The mtime guard
keeps this from happening **when nothing was rewritten** (ASCII-only inputs
preserve their mtime), but the first build after introducing Unicode into
your source will cost one extra `latexmk` pass.

## Cheat sheet

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `! LaTeX Error: Unicode character … not set up for use with LaTeX` | Engine is pdflatex; codepoint is unmapped or `pylatexenc` is missing | Install `pylatexenc`, or switch engine, or escape the char in the source |
| Reference shows literal `¡i¿…¡/i¿` | CrossRef-style HTML markup in the `.bib`, and you're on a texmark < v0.12.1 | Upgrade texmark |
| `δ` appears in PDF as a missing glyph | Same as above, fixed by rewrite | Upgrade texmark |
| `WARNING … has no LaTeX replacement` | Char is genuinely unmapped | Edit `.bib` entry; or switch engine; or extend `unicode_bib._OVERRIDES` |
| Reference superscripts look like two separate blocks (`¹⁸` rendered as `1` then `8`) | Pre-v0.12.1 texmark, no merge step | Upgrade texmark |
| Body Unicode in markdown not converted | Engine is `lualatex` or `xelatex` | Either let those engines handle UTF-8 natively (they do), or switch to `engine: pdflatex` |

## Performance

Profiled on real inputs (avg of 10 runs):

| Input | Size | Rewrite cost |
| --- | --- | --- |
| Small ASCII (`.tex` snippet) | 7 KB | 0.5 ms |
| Typical 10-page paper, ASCII | 70 KB | 4 ms |
| Book-length, ASCII | 700 KB | 44 ms |
| Sparse Unicode (realistic) | 30 KB | 2 ms |
| Unicode-heavy (worst case) | 25 KB | 19 ms |

All numbers are negligible compared to a single pdflatex pass (1–3 s on a
typical paper). The ASCII-only path skips the write entirely.

## See also

- [docs/preamble.md](preamble.md) — when you need to inject your own LaTeX
  preamble (the encoding layer doesn't get in your way).
- [texmark/unicode_bib.py](../texmark/unicode_bib.py) — the implementation,
  with extensive inline comments on why each step exists.
- [pylatexenc on PyPI](https://pypi.org/project/pylatexenc/) — the underlying
  Unicode → LaTeX mapping table.
