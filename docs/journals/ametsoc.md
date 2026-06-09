# AMS — Journal of Climate, JAS, MWR, BAMS, …

**Template name:** `ametsoc`
**Aliases:** `jclim`, `jas`, `mwr`, `jamc`, `jhm`, `jpo`, `jtech`, `waf`, `bams`, `amsoc`
**Class file:** [ametsocV6.1.cls](https://github.com/perrette/texmark/blob/main/texmark/templates/ametsoc/ametsocV6.1.cls) (AMS LaTeX Package v6.1, Sept 2021)
**Citation style:** natbib with AMS `\bibpunct`
**Example PDF:** [build/example-ametsoc.pdf](https://github.com/perrette/texmark/blob/main/build/example-ametsoc.pdf)

## Covers

| journal | abbreviation |
| --- | --- |
| Journal of Climate | J. Climate |
| Journal of the Atmospheric Sciences | JAS |
| Monthly Weather Review | MWR |
| Journal of Applied Meteorology and Climatology | JAMC |
| Journal of Hydrometeorology | JHM |
| Journal of Physical Oceanography | JPO |
| Journal of Atmospheric and Oceanic Technology | JTECH |
| Weather and Forecasting | WAF |
| Bulletin of the American Meteorological Society | BAMS |

The AMS class doesn't distinguish journals at compile time — the journal is
selected at submission on the AMS portal. The aliases all resolve to the
same template, so you can write `template: jclim` for clarity but the
output is identical to `template: ametsoc`.

## YAML setup

```yaml
journal:
    template: ametsoc
    options: twocol      # default — 2-column journal-style preview
    # options: ""        # 1.5-spaced AMS submission style (REQUIRED for actual submission)
```

> The default `twocol` produces the journal-style preview look. **For real
> submission to AMS, you must remove the `twocol` option**: AMS requires the
> 1.5-spaced single-column submission layout.

## Recognised section headings

- `# Abstract`
- `# Significance` / `# Significance Statement` — required for J. Climate, JAS, MWR, JAMC, JHM, JPO, JTECH, WAF
- `# Capsule` — required for BAMS only, ≤30 words
- `# Data Availability`
- `# Acknowledgments`
- `# Appendix` / `# Supplementary Information`

The template emits `\statement{...}` (significance) or `\capsule{...}`
(BAMS), switching to `\twocolsig{...}` / `\twocolcapsule{...}` automatically
when `twocol` is in the options.

## Gotchas

- The AMS `\abstract{}` command is defined with `\def` (not `\long\def`), so
  it cannot contain paragraph breaks. The template collapses newlines in
  the abstract to spaces automatically.
- Affiliation indices in the YAML can be integers or strings. Integers are
  converted to letters (1 → a, 2 → b, …) to match the `\aff{a}` convention
  AMS uses. String values pass through unchanged, so for multi-affiliation
  authors you can write `affiliation: "a,c"`.
