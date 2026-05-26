# Copernicus / EGU journals

**Template name:** `copernicus`
**Aliases:** `cp`, `esd` (and any other Copernicus abbreviation registered as a filter)
**Class file:** [copernicus.cls](../../texmark/templates/copernicus/copernicus.cls)
**Citation style:** natbib author-year
**Example PDF:** [build/example.pdf](../../build/example.pdf)

## Covers

All EGU / Copernicus journals — short form abbreviations are passed to the
class via `journal.short`:

| short | journal |
| --- | --- |
| `acp` | Atmospheric Chemistry and Physics |
| `amt` | Atmospheric Measurement Techniques |
| `bg` | Biogeosciences |
| `cp` | Climate of the Past |
| `esd` | Earth System Dynamics |
| `essd` | Earth System Science Data |
| `hess` | Hydrology and Earth System Sciences |
| `nhess` | Natural Hazards and Earth System Sciences |
| `tc` | The Cryosphere |
| `wcd` | Weather and Climate Dynamics |

…and the full list at <https://publications.copernicus.org>.

## YAML setup

```yaml
journal:
    template: copernicus
    short: cp        # journal abbreviation: cp, acp, hess, tc, esd, bg, ...
```

`journal.short` becomes the documentclass option, e.g.
`\documentclass[cp, manuscript]{copernicus}`. `manuscript` is the
discussion preprint style; Copernicus typesets the production layout
themselves.

## Recognised section headings

These can appear as `# ...` headings in your markdown — texmark will pull
them out of the body and inject them into the right LaTeX command:

- `# Abstract`
- `# Acknowledgements`
- `# Author Contributions`
- `# Competing Interests`
- `# Appendix`
- `# Supplementary Material` / `# Supplementary Information`
