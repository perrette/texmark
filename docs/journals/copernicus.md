# Copernicus / EGU journals

**Template name:** `copernicus`
**Aliases:** `cp`, `esd` (and any other Copernicus abbreviation registered as a filter)
**Class file:** [copernicus.cls](https://github.com/perrette/texmark/blob/main/texmark/templates/copernicus/copernicus.cls)
**Citation style:** natbib author-year
**Example PDF:** [build/example.pdf](https://github.com/perrette/texmark/blob/main/build/example.pdf)

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
    short: cp            # journal abbreviation: cp, acp, hess, tc, esd, bg, ...
    # draft: false       # publication-ready two-column production layout
```

`journal.short` is always passed as the first documentclass option. The
layout follows the unified [`journal.draft`](../yaml-reference.md#journaldraft)
flag:

- `draft: true` (default) → `\documentclass[cp, manuscript]{copernicus}` —
  the one-column, line-spaced discussion/preprint layout authors submit.
- `draft: false` → `\documentclass[cp]{copernicus}` — the two-column typeset
  production layout (the class sets `\@twocolumntrue` when the journal stage
  is final and `manuscript` is absent).

The journal logo, coloured section bars and a few other decorative production
elements only appear when `copernicuslogo.pdf` is present in the build
directory, so `draft: false` is a close preview rather than the exact
published page. Set `journal.options` explicitly to override the flag.

## Recognised section headings

These can appear as `# ...` headings in your markdown — texmark will pull
them out of the body and inject them into the right LaTeX command:

- `# Abstract`
- `# Acknowledgements`
- `# Author Contributions`
- `# Competing Interests`
- `# Appendix`
- `# Supplementary Material` / `# Supplementary Information`

## Bundled fonts

`copernicus.cls` does `\RequirePackage[T5,T3,T1]{fontenc}`, so it needs the
T5 (Vietnamese) encoding from the `vntex` package. That package is absent on
minimal TeX installs, where the build otherwise fails with
`Encoding file 't5enc.def' not found` followed by an NFSS error. To keep the
template self-contained, the two files needed to satisfy the encoding setup —
`t5enc.def` and `t5cmr.fd` (LPPL, from vntex) — are bundled in the template
directory and copied into the build directory at build time. They are the
standard, long-frozen vntex files, only ever parsed to register the T5
encoding (no Vietnamese glyph is typeset), so they do not affect the output on
systems that already ship vntex.
