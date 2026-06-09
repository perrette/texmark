# Live preview (`--watch`)

```bash
texmark sources/main.md --pdf --watch
```

Rebuilds whenever the input markdown, bibliography, or template changes.
Combine with an auto-reloading PDF viewer (zathura, evince, okular) for a
live-preview workflow — the output PDF is rewritten in place so viewers
that follow inode changes keep your scroll position.

In multi-file projects `--watch` also tracks every embedded chapter and
every companion document (plus each companion's bibliography and template).
See [Multi-file projects](multi-file.md) for the details.
