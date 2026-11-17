# Design notes: source ↔ PDF synchronisation (SyncTeX for Markdown)

Status: steps 1–4 implemented (SyncTeX output, lighter map, `texmark sync`,
`--wrap=preserve`). The block-level map (3b) is not planned: the lighter map
with word matching finds the exact line for most lines (153 of 167 typeset
lines of the thesis chapters round-trip exactly). Step 5 (Evince/Papers helper,
VS Code commands) is on hold. Written for the agent that implements it in
texmark; the consumers are papers-write, VS Code (texmark-vscode) and GNOME
Papers/Evince.

## Goal

For a document built with texmark:

- **Forward search**: a position in a Markdown source (file, line, optionally
  column) → the place in the PDF (page and a rectangle).
- **Backward search**: a point in the PDF (page, x, y) → the Markdown source
  file and line.

It must work for one-file papers and for multi-file books (`\include`d
chapters, `--only`, `--keep-pages`), with the caches (texcache, blockcache),
`--progressive` and `--watch`. Consumers must not need to know texmark's
internals: they use a stable file format or a CLI.

## Current state (as found on 2026-11-17)

- No SyncTeX: neither `_engine_cmd` (build.py ~718) nor the latexmk command
  (build.py ~800) passes `-synctex=1`; tectonic is not given `--synctex`.
- No Markdown → TeX position information: `parse_markdown`
  (project.py ~80–95) reads with pandoc `markdown+footnotes`, which keeps no
  source positions; CriticMarkup is rewritten into spans before pandoc
  (project.py ~90).
- blockcache.py already splits a document into top-level blocks and reuses
  their LaTeX; chapters are separate `.tex` files under `\include`.
- `synctex` (TeX Live's CLI) is installed at /usr/bin/synctex.

## Design

### 1. SyncTeX output

- Pass `-synctex=1` to every engine run (pdflatex/xelatex/lualatex directly,
  through latexmk with `-synctex=1`, tectonic with `--synctex`). Default on;
  `--no-synctex` turns it off.
- The `.synctex.gz` must sit next to the published PDF with the same stem
  (`build/thesis.pdf` → `build/thesis.synctex.gz`). Tools find it by name.
  When `-o` renames the PDF or a job name differs (`<stem>-draft`,
  `<stem>-part-draft` in `--progressive`), copy or rename the synctex file
  the same way.
- In `--watch`, publish the synctex file together with the PDF, synctex
  first, then the PDF, both by write-to-temp and rename. That way a consumer
  that sees a new PDF also sees its matching synctex file.
- Draft passes (`--progressive`, figures as boxes) produce valid synctex
  data for their PDF too; publish it with the draft PDF.

### 2. The Markdown → TeX map (the new part)

SyncTeX links PDF positions to **TeX** lines. texmark adds a map from
generated TeX lines back to Markdown lines.

**Producing positions.** pandoc's `markdown` reader gives no positions, and
switching to `commonmark_x+sourcepos` would change the accepted syntax. Do
not do that. Instead:

1. Find the source line range of each top-level block by texmark's own
   scan of the Markdown. Blank-line-separated blocks, fenced code, lists,
   tables, YAML front matter, footnote definitions and HTML comments must be
   handled. Match the scanned blocks to pandoc's top-level blocks in order,
   and check the count. blockcache already reasons about top-level blocks;
   reuse its segmentation if possible.
2. Account for the CriticMarkup rewrite (project.py ~90). Either keep it
   line-preserving (the rewritten text has the same number of lines; check
   this), or record an offset table during the rewrite.
3. Write each block's LaTeX with a marker comment on the line before it:
   `%%md introduction.md:123`. Comments do not change the output. Add the
   markers when the LaTeX is assembled, not in the pieces that blockcache
   stores: a cached block keeps its hash when the text above it moves, so a
   stored line number would go stale.
4. Within a block, use pandoc `--wrap=preserve`, so that a paragraph's TeX
   lines follow its Markdown lines. Check that this does not change the
   output or break blockcache's byte-for-byte guarantee. Where it cannot be
   used, map to the block's first line only.

**The map file.** After writing the `.tex` files, write
`<pdf-stem>.srcmap.json` next to the published PDF from the markers. This
file is the contract: consumers read it, not the comments. The block map is
the `blocks` key of the same file that holds the lighter map's `units`
(2b); `units` is always present.

```json
{
  "version": 1,
  "pdf": "thesis.pdf",
  "pdf_size": 1234567,
  "generated": "2026-11-17T12:00:00Z",
  "build": "sha256:<hex digest of the published PDF>",
  "units": [ … ],
  "blocks": {
    "/abs/build/thesis.tex": [
      {"tex": [120, 134], "md": "/abs/thesis.md", "line": [40, 52]}
    ],
    "/abs/build/introduction.tex": [
      {"tex": [1, 9], "md": "/abs/introduction.md", "line": [1, 9], "exact": true}
    ]
  }
}
```

- `version`: 1. Readers ignore keys they do not know, so adding a key does
  not change the version; it changes only when a key changes meaning.
- `build`: `sha256:` and the hex digest of the published PDF. `pdf_size`:
  its size in bytes. A reader compares the size first and hashes the PDF
  only when the sizes match.
- `blocks`: per `.tex` file, the blocks it holds. `tex`: an inclusive range of TeX lines. `md` and `line`: the source file
  and its inclusive line range. `exact: true` means the lines correspond one
  to one (`--wrap=preserve` held). Otherwise lines inside the range are
  interpolated, or mapped to the first line.
- Paths are absolute with symlinks resolved (realpath), in the map and in
  what texmark passes to `synctex`. SyncTeX records `/abs/build/./x.tex`;
  normalise it the same way. `synctex view` only matches a TeX file given by
  its absolute path.
- Lines that come from the template (preamble, title page, bibliography)
  have no entry. A lookup there finds nothing, or the nearest block before.
- Publish it with the PDF and synctex file: synctex file, map, PDF. Each
  stage of `--progressive` publishes its own (the `build` differs).

### 2b. Cost: the map must not slow the build

Requirement: with synctex and the map on, a build (and each `--watch`
rebuild) is not measurably slower than without; aim for less than 2% of the
build time, measured on the thesis (`make watch` / `make full`).

Expected costs, to measure and not assume:

- `-synctex=1`: a few percent of each LaTeX run, plus writing a gzip file.
  This is the usual price of SyncTeX in every LaTeX editor.
- The block scan: one pass over each Markdown file, done only when the file
  changed. texcache and blockcache already skip unchanged chapters and
  blocks, and their markers come with their cached LaTeX.
- Writing `srcmap.json`: small, one file per build.
- `--wrap=preserve`: no cost, but it may change the output. Check this.

If block-level mapping costs too much, or if keeping markers through
blockcache gets complicated, use the **lighter map** below and find the exact
place on demand.

**Lighter map (fallback).** `srcmap.json` maps only coarse units, and the
consumer finds the exact line by searching the text when asked:

```json
{
  "version": 1,
  "pdf": "synopsis.pdf",
  "pdf_size": 1234567,
  "generated": "2026-11-17T12:00:00Z",
  "build": "sha256:…",
  "units": [
    {"md": "/abs/introduction.md", "line": [1, 410], "tex": "/abs/build/introduction.tex", "texline": [1, 380],
     "sections": [{"title": "Introduction", "line": 1, "texline": 1}, {"title": "Sea level", "line": 37, "texline": 33}]}
  ]
}
```

- `units`: one per source file (chapter) with its line ranges in Markdown
  and TeX. `sections`: each heading's Markdown and TeX line. texmark knows
  both while it writes the chapter, so this costs almost nothing.
- **Backward:** SyncTeX gives `TEXFILE:TEXLINE`. The unit and section narrow
  it to a stretch of Markdown. The consumer takes the words of the TeX line
  (or of the PDF text clicked), with LaTeX commands stripped, and searches
  for them in that stretch with a tolerant pattern (whitespace and
  punctuation loose, Markdown emphasis ignored).
- **Forward:** the section of the Markdown line gives a TeX range. Search
  the TeX for the line's words in that range, then run
  `synctex view` on the line found.

Both maps coexist in one file: the consumer uses `blocks` when present,
otherwise `units`. `sections[].title` is the heading's plain text. A heading
that a filter moved out of the body (an abstract section) has no TeX line
and is left out. With `--only`, `units` lists the root and the chapters
typeset; companion documents have their own PDF and map. Start with whichever proves cheap enough; the lighter map is enough
for multi-file documents, which is its main use.

### 2c. How an editor finds the files (no editor settings)

The files beside the PDF are the whole contract; editors need no
configuration.

- **From a PDF** `X.pdf`: read `X.synctex.gz` and `X.srcmap.json` from the
  same folder.
  - Both present: Markdown positions.
  - Only `X.synctex.gz`: TeX positions. This also covers a pure LaTeX
    project built with `-synctex=1` by any tool.
  - Neither: the editor may fall back to searching the clicked text in the
    project's source files.
- **From a source file** `F.md`: find the PDF whose `srcmap.json` lists `F.md`.
  Look in the build folders under the project (`build/`, `build-*/`). If
  several PDFs list it (a synopsis and a full build), take the most recently
  built one, or ask. For a `.tex` source, look for a `.synctex.gz` that
  mentions it.
- The map's `build` field must match the PDF it sits beside (compare
  `pdf_size` first, then the sha256). A map that does not match (a build
  that failed half-way) is ignored.

### 3. A CLI for consumers

```
texmark sync forward  SOURCE.md:LINE[:COL] [--pdf build/thesis.pdf]   → JSON
texmark sync backward --pdf build/thesis.pdf PAGE X Y                → JSON
```

- **forward**: map `SOURCE.md:LINE` to `TEXFILE:TEXLINE` with the map, run
  `synctex view -i TEXLINE:COL:TEXFILE -o PDF`, and print
  `{"page", "x", "y", "width", "height"}` (PDF points, origin top left, as
  synctex gives them; say so in the output). If there are several records,
  print a list.
- **backward**: run `synctex edit -o PAGE:X:Y:PDF` to get `TEXFILE:TEXLINE`,
  map back with the map, and print `{"file", "line", "column"}`. Column may
  be null.
- When `--pdf` is omitted, find the PDF from the project
  (`build/<root-stem>.pdf`, or `-o` as recorded in the map).
- Exit with a non-zero status and a JSON error when the map or synctex file
  is missing, or when the map's `build` does not match the PDF (stale).
- Also expose the same two functions in Python (`texmark.sync`).

### 4. Consumers

- **papers-write** (the Tauri app): a Ctrl+click in its pdf.js view gives
  (page, x, y) and calls `texmark sync backward`, or reads
  `<stem>.srcmap.json` and runs `synctex` itself. It then opens the source at
  that line. "Show in PDF" from the editor uses `forward`. For a pure LaTeX
  project, papers-write uses synctex directly without the map.
- **GNOME Papers / Evince** (the current viewer of the thesis workflow):
  they speak SyncTeX over D-Bus with **TeX** file names:
  - backward: the `SyncSource` signal gives a TeX file and line;
  - forward: the `SyncView` method takes a TeX file and line.

  A small helper, `texmark sync evince [--editor "code -g {file}:{line}"]`,
  can listen for `SyncSource`, map it to Markdown and run the editor command.
  For forward search it maps Markdown to TeX and calls `SyncView`. This
  gives the existing VS Code + Papers setup both directions without a new
  viewer. The D-Bus interface is `org.gnome.evince.Daemon` /
  `org.gnome.evince.Window`; check the names for GNOME Papers, which may
  have renamed it.
- **VS Code (texmark-vscode)**: add commands *texmark: Show in PDF*
  (forward, via the CLI, then focus the viewer) and a handler for the
  backward direction, either from the Evince helper or from LaTeX Workshop's
  viewer if it is used. Keep it optional; the extension today only extends
  the Markdown preview.

### 5. Edge cases to handle or document

- `--only` / `--keep-pages`: the map covers the chapters that were built.
  Pages kept blank have no records.
- Figures, tables and equations: map to the block containing them. Floats
  that move to another page still map back to their source block.
- Footnotes: their text is defined elsewhere in the Markdown (`[^1]: …`).
  Map the footnote's TeX to the definition's lines if the scan can tell;
  otherwise to the referencing paragraph.
- Citations and cross-references: inline, no special handling.
- Journal templates that move the abstract or other blocks out of the body:
  the marker travels with the block, so the map still holds.
- Precompiled preamble (`.fmt`): no effect; the body is still read from the
  `.tex` files.
- Windows paths and non-ASCII file names: SyncTeX quirks. Normalise paths
  and test one non-ASCII name.

### 6. Tests

- A fixture project: front matter, headings, paragraphs (several lines
  each), a list, a footnote, a figure, display math with a label,
  CriticMarkup, and two chapters under `\include`.
- Build with synctex on. For a sample of Markdown lines in each block,
  `forward` then `backward` must return the same file and a line within ±1
  (exact blocks: the same line).
- The map must be the same whether a chapter came from blockcache or a full
  conversion. Build twice, edit one paragraph, build again, and compare.
- `--watch`: after a change, the published PDF, synctex file and map carry
  the same `build`.
- Skip the synctex-dependent tests when `synctex` is not installed.

### 7. Order of work

1. `-synctex=1` everywhere, with the synctex file published next to the PDF.
   This alone gives pure-LaTeX users forward and backward search.
2. `srcmap.json` with the lighter map (units and sections, 2b): cheap and
   enough for multi-file documents.
3. `texmark sync forward|backward` and the Python API. It runs on each
   click in an editor: keep its start-up time short, and measure it.
3b. The block-level map (block scan, markers, single-file documents first,
   then `\include`d chapters and blockcache), measured against the 2%
   budget and added only if it stays within it. The markers are added when
   the LaTeX is assembled, not stored in blockcache's pieces: a cached block
   keeps its hash when the text above it moves, so a stored line number
   would go stale.
4. `--wrap=preserve` for line-exact paragraphs, if it keeps outputs
   identical.
5. The Evince/Papers helper, then the VS Code commands.
