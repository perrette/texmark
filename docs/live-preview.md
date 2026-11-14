# Live preview (`--watch`)

```bash
texmark sources/main.md --pdf --watch --progressive
```

This is the recommended command while writing. texmark builds the document,
then rebuilds it whenever the input markdown, an embedded chapter, a
companion document, the bibliography or the template changes. Combine it
with a PDF viewer that reloads the file when it changes (zathura, evince,
okular, GNOME Papers). The output PDF is written to a temporary file next to
it and renamed over the previous one, so a viewer never reads a half-written
file.

## What happens on a save

The markdown is converted to LaTeX (chapters whose source did not change keep
their `.tex`, see [Multi-file projects](multi-file.md)), then the PDF is
built in stages, each of which replaces the output PDF
([Progressive builds](build-backends.md#progressive-builds)):

1. One LaTeX pass with figures as boxes (the draft job, `<stem>-draft`),
   from the precompiled preamble when there is one. References from the
   previous build are reused; labels and citations added since show as `??`.
   When the files that changed are all chapters of a book-family document
   (`chapters:` or `![](chapter.md)` in the root, which LaTeX `\include`s),
   this pass typesets only those chapters, as the job `<stem>-part-draft`
   (see below).
2. The draft job with references and bibliography resolved (latexmk: bibtex
   and further passes where needed).
3. The full build with figures. Skipped with `--draft`.

Stages 2 and 3 run in the background while texmark keeps watching the
sources. Each published PDF is announced with the time since the change
was seen (here an edit to the first chapter of an 83-page thesis synopsis;
the part job typesets 24 pages):

```
texmark: draft PDF of introduction (1 pass) written: build/synopsis.pdf (0.8 s)
texmark: draft PDF (references resolved) written: build/synopsis.pdf (2.3 s)
texmark: PDF with figures written: build/synopsis.pdf (4.8 s)
```

The sources are checked twice a second, so the time from the save is up to
0.5 s longer.

Without `--progressive`, each change runs a single plain build (or a draft
build with `--draft`), also in the background and stopped by a new change in
the same way.

## A save during a build

A new change stops the stages still running for the previous one: texmark
sends SIGTERM to the LaTeX tools (pdflatex, latexmk, bibtex; each runs in
its own process group, so the processes latexmk started are stopped with
it), SIGKILL after 2 seconds if they are still there, and waits until they
are gone. A LaTeX run stopped half-way leaves `.aux` files with only part of
the labels and citations, so before each stage texmark saves the files the
LaTeX jobs write (`.aux` including the chapter `.aux` files, `.bbl`, `.toc`,
`.log`, `.fdb_latexmk`; not the `.tex` files, the precompiled preamble or
the job PDFs, which no LaTeX pass reads, except `<build>/<stem>.pdf` when it
is the output PDF) to `<build>/.texmark-snapshot/`, and puts them back when the stage
is stopped. Then stage 1 starts for the new change. A stage of an older change
never replaces the PDF of a newer one.

Before every LaTeX pass and latexmk run (in any build, not only `--watch`),
texmark also checks the `.aux` files in the build directory: braces
balanced, a complete last line, a chapter `.aux` ending with the closing of
its `\@setckpt{<chapter>}{...}`, and a main `.aux` ending with
`\gdef \@abspage@last{<n>}` when it has that line. An `.aux` that fails (left
by a run killed from outside, for example) is restored from the snapshot
when there is a good copy there, and deleted otherwise. If a run still stops
with "File ended while scanning use of ..." or "File ended within \read" on
an `.aux`, that file is deleted and the run is repeated once.

A change saved while the markdown is being converted to LaTeX is picked up
when the conversion has finished.

## Chapter edits in a book

When only chapters changed, stage 1 typesets these chapters only: the
generated `.tex` has a line after the preamble that makes the job
`<stem>-part-draft` read `<build>/<stem>-part-setup.tex`, which texmark
writes with the `\includeonly{...}` of the changed chapters. The page
numbers, chapter numbers and references of the other chapters come from
their `.aux` files, written by the previous build, so the pages are numbered
as in the whole document. The other chapters are blank pages, as many as
they had in the previous build (see `--keep-pages` in
[Multi-file projects](multi-file.md)), so the PDF has the same pages as the
whole document and the viewer stays on its page. The part job starts from
the draft job's `.aux` and `.bbl` (citations, contents lines), and typesets
the reference list of the master document (`\bibliography` after the
chapters) into a box that is never output, so it takes no pages (citations
stay defined; a biblatex `\printbibliography`, or a `\bibliography` inside a
chapter, is typeset as usual). The stage is announced as `draft PDF of
<chapter> (1 pass)`, and the viewer shows these chapters until stage 2
publishes the whole document.

This needs pdflatex. With `--only`, it applies to the chapters in the
`--only` list; changes to other files (the root, the bibliography, a
chapter outside the list) run the usual stage 1.

## One texmark per build directory

Every texmark run takes a lock on `<build>/.texmark.lock` (`flock`): a
one-off build for its duration, a watch session until it stops. A second
texmark on the same build directory waits for a one-off build to finish,
and exits with an error when a watch session holds the directory:

```
texmark: the build directory build is used by a texmark --watch session (pid 12345); stop it or build in another directory (-d).
```

## Stopping

Ctrl+C, SIGTERM or SIGHUP (closing the terminal) stop the watch session: the
running LaTeX tools are stopped as above, the saved files are put back when a
stage was stopped half-way, and the lock is released. A snapshot left by a
texmark that was killed (`kill -9`, crash) is restored by the next texmark
run on that build directory before it builds.

## Watched files

In multi-file projects `--watch` also tracks every embedded chapter and
every companion document (plus each companion's bibliography and template).
See [Multi-file projects](multi-file.md) for the details.
