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

In multi-file projects `--watch` also tracks every embedded chapter and
every companion document (plus each companion's bibliography and template).
See [Multi-file projects](multi-file.md) for the details.
