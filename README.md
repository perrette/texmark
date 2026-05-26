# texmark

Write scientific articles in markdown


## Installation

for development, after cloning:

    pip install -e .

and soon:

    pip install texmark

## Example

See [example.md](example.md) for a sample markdown file with yaml metadata in the header.

The command to convert the markdow to tex is:

    texmark example.md

And to convert to PDF

    texmark example.md --pdf

For another journal, it is enough to change the `journal -> template' field in the yaml metadata.
For testing it is also possible to pass `-j` for `--journal-template`:

    texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex

See the example tex and pdf results in [build](/build)

Available journal templates:

| template name | publisher / journals |
| --- | --- |
| `copernicus` (aliases: `cp`, `esd`, ...) | Copernicus (EGU journals: ACP, BG, CP, ESD, HESS, NHESS, TC, ...) |
| `science` | AAAS Science |
| `ametsoc` (aliases: `jclim`, `jas`, `mwr`, `bams`, ...) | American Meteorological Society — Journal of Climate, JAS, MWR, BAMS, ... |
| `arxiv` (alias: `preprint`) | Generic arXiv-style preprint (article class) |
| `elsarticle` (alias: `elsevier`) | Elsevier — QSR, EPSL, GPC, Earth-Science Reviews, Cell, Lancet, ... |
| `agujournal` (aliases: `agu`, `jgr`, `grl`, `james`, `wrr`, ...) | American Geophysical Union — JGR family, GRL, Earth's Future, JAMES, ... |
| `springernature` (aliases: `nature`, `naturecomms`, `natclimchange`, `natgeoscience`, `scirep`) | Springer Nature — Nature, Nature Communications, Nature Climate Change, Nature Geoscience, Scientific Reports, ... |
| `pnas` | PNAS — Proceedings of the National Academy of Sciences of the USA |
Only partial support is provided. Upon submission you'll most likely need
to rework the final latex version, especially to handle things like appendix or special sections.
Alternatively, you may write your custom template (see the advanced section)

## Collect figures and tables at the end of the document

Just add
```yaml
collect_figures_and_tables: true
```
to your markdown yaml metadata.


## Advanced: latex template

The templates are written in [jinja2](https://jinja.palletsprojects.com).

Just copy from e.g. texmark/templates/science/template.tex to your own, e.g. custom_template.tex
And run again with:

    texmark example.md --pdf -j science -o build/example-science.pdf --tex build/example-science.tex --template custom_template.tex

The -j journal template option (here `science`) is still used to set custom filters (e.g. only `\cite` for Science, no `\citet` ; extract specific sections as metadata to be injected as `{{section}}` instead of `{{body}}` etc). The machinery is defined in [texmark/filters.py](/texmark/filters.py) and can in principle be extended or copied.
Two approaches are possible:
- just add more filters via the `--filters` command or in the yaml metadata.
- extend the existing filters in a module, e.g. custom_filter.py, that extends the `filters` dict from the `texmark.filters` module (see the source code to check the details). And then pass it via `--filters-module custom_filter` parameter (or `custom_filter` in the metadata) to prompt the texmark filter to load that module and make it available via `-j your-custom-name`. Note that will require you to explicitly pass `--template` as well. Unless you overwrite an existing filter.