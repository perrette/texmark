# Figure paths

texmark interprets `![](path)` URLs by the same rules as GitHub's markdown
renderer:

- **No leading slash** — relative to the markdown file's directory
  (the standard markdown spec).
- **Leading slash** — relative to the project root. By default the
  project root is detected via `git rev-parse --show-toplevel`, run from
  the markdown's directory so submodules and worktrees resolve to their
  own root rather than the outer repo's. For non-git projects, the
  invocation directory (CWD) is used. You can override either by passing
  `--project-root <path>` on the CLI (or `project_root: <path>` in the
  yaml front-matter).

Once resolved, each URL is rewritten in the generated `.tex` to be
relative to the build directory. The figure files stay where they are on
disk; nothing is copied.

If you would rather have short paths in the `.tex` (e.g. `eof.png`
instead of `../images/eof.png`), pass `--figure-folders <dir> [<dir> ...]`
on the CLI (yaml: `figure_folders: [<dir>, ...]`). Each folder is
interpreted relative to the current working directory and feeds LaTeX's
`\graphicspath`. Figures that live under any of these folders get short
URLs in the `.tex`; figures elsewhere keep the relative-to-build-dir form.
Folder search order is respected (first match wins, matching pdflatex's
own resolution).

For a self-contained build (e.g. to hand the `.tex` + figures to a
journal portal), pass `--copy-figures` on the CLI (yaml:
`copy_figures: true`). In that mode every referenced figure is copied
flat into `<build>/figures/`:

- Files keep their basename when unique.
- When two figures share a basename but have different contents, both are
  renamed to `<stem>-<short-content-hash><ext>` for disambiguation.
- Same file referenced from multiple paths collapses to a single bundled
  copy.
- A `.texmark-figures` manifest in `<build>/figures/` records which files
  texmark wrote, so the next build can delete only files it owns; files
  you put there by hand are preserved.

`--figure-folders` is ignored when `--copy-figures` is set (every figure
ends up in `<build>/figures/` either way).

Remote (`http(s)://`) figure URLs are always downloaded into
`<build>/figures/<hash>/<basename>` by the `texmark-download-images`
filter, regardless of these settings.

## Collect figures and tables at the end of the document

Just add

```yaml
collect_figures_and_tables: true
```

to your markdown yaml metadata.
