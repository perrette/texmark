# Live preview (`--watch`)

```bash
texmark sources/main.md --pdf --watch
```

Rebuilds whenever the input markdown, bibliography, or template changes.
Combine with an auto-reloading PDF viewer (zathura, evince, okular) for a
live-preview workflow. The output PDF is written to a temporary file next to
it and renamed over the previous one, so a viewer never reads a half-written
file. Viewers that watch the file for changes reload it after the rename
(checked with GNOME Papers).

For a faster first view after each change, add `--progressive`:

```bash
texmark sources/main.md --pdf --watch --progressive
```

Each rebuild then publishes a draft PDF after one LaTeX pass (figures as
boxes, references from the previous build), then with the references
resolved, then with the figures. See
[Progressive builds](build-backends.md#progressive-builds). A change saved
while a rebuild runs is picked up when that rebuild has finished.

In multi-file projects `--watch` also tracks every embedded chapter and
every companion document (plus each companion's bibliography and template).
See [Multi-file projects](multi-file.md) for the details.
