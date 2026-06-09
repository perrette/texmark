# Quickstart

See [example.md](https://github.com/perrette/texmark/blob/main/example.md) for a
sample markdown file with yaml metadata in the header.

The command to convert the markdown to tex is:

```bash
texmark example.md
```

And to convert to PDF:

```bash
texmark example.md --pdf
```

For another journal, it is enough to change the `journal -> template` field in the yaml metadata.
For testing it is also possible to pass `-j` for `--journal-template`:

```bash
texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex
```

See the example tex and pdf results in
[build/](https://github.com/perrette/texmark/tree/main/build).

## Where to go next

- [Pick a journal template](journals/index.md) for your target journal.
- [YAML reference](yaml-reference.md) — every front-matter field, in one place.
- [Build backends and engines](build-backends.md) — latexmk, tectonic, pdflatex/xelatex/lualatex.
- [Live preview](live-preview.md) — rebuild on save with `--watch`.
