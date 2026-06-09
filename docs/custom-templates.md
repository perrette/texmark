# Custom LaTeX templates

The templates are written in [jinja2](https://jinja.palletsprojects.com).

Just copy from e.g. `texmark/templates/science/template.tex` to your own, e.g.
`custom_template.tex`, and run again with:

```bash
texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex --template custom_template.tex
```

The `-j` journal template option (here `science`) is still used to set custom
filters (e.g. only `\cite` for Science, no `\citet`; extract specific sections
as metadata to be injected as `{{section}}` instead of `{{body}}`, etc.). The
machinery is defined in the
[`texmark/filters/`](https://github.com/perrette/texmark/tree/main/texmark/filters)
package and can in principle be extended or copied.

Two approaches are possible:

- Just add more filters via the `--filters` command or in the yaml metadata.
- Extend the existing filters in a module, e.g. `custom_filter.py`, that extends
  the `filters` dict from the `texmark.filters` module (see the source code to
  check the details). Then pass it via `--filters-module custom_filter`
  (or `custom_filter` in the metadata) to prompt the texmark filter to load that
  module and make it available via `-j your-custom-name`. Note that will require
  you to explicitly pass `--template` as well — unless you overwrite an existing
  filter.
