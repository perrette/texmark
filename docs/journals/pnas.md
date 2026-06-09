# PNAS

**Template name:** `pnas`
**Class file:** [pnas-new.cls](https://github.com/perrette/texmark/blob/main/texmark/templates/pnas/pnas-new.cls) (PNAS 2024 LaTeX bundle)
**Citation style:** natbib `[numbers, sort&compress]` → rewritten to `\cite{}`
**Example PDF:** [build/example-pnas.pdf](https://github.com/perrette/texmark/blob/main/build/example-pnas.pdf)

## Covers

- Proceedings of the National Academy of Sciences of the USA (PNAS)
- PNAS Nexus

## YAML setup

```yaml
journal:
    template: pnas
    options: [9pt, twocolumn, twoside]    # default — PNAS journal style
    classification: "Research Article"     # optional, top-of-page tag (\articletype)
    templatetype: pnasresearcharticle      # research / brief / mathematics / invited
    doi: "10.1073/pnas.XXXXXXXXXX"         # optional, fills the \doi{} line
    displaywatermark: false                # default — set true to print the DRAFT watermark
```

### Article type variants (`templatetype`)

| value | matching .sty file | description |
| --- | --- | --- |
| `pnasresearcharticle` | bundled | two-column research article (default) |
| `pnasbriefreport` | not bundled | brief report layout |
| `pnasmathematics` | not bundled | single-column mathematics |
| `pnasinvited` | not bundled | invited submission |

Only the research-article variant ships with texmark. For the others, drop
the official `.sty` from the PNAS LaTeX package into
`texmark/templates/pnas/` and set `templatetype` accordingly.

## PNAS-specific sections

- `# Significance` / `# Significance Statement` — 50–120 words, broad
  audience; rendered into `\significancestatement{}` (auto-floated into a
  blue box on page 1)
- `# Equal Authors` — note about equal contribution
- `# Author Contributions` — rendered into `\authorcontributions{}`
- `# Competing Interests` / `# Declaration` / `# Author Declaration`
- `# Data Availability` — rendered into `\dataavailability{}`
- `# Acknowledgments` — rendered into `\acknow{}` + `\showacknow{}`

Keywords are pipe-separated as PNAS expects (`Keyword 1 $|$ Keyword 2 $|$ ...`).

## Layout flow

PNAS uses special wrappers around the body to switch between the
wide-column first paragraph and the standard 2-column layout. The template
emits them automatically:

- `\Firstpage` immediately before the body — switches to the wide-column
  intro layout PNAS uses for the first paragraph(s)
- `\Endparasplit` immediately after the body — clearpages and returns to
  standard 2-column for the references and back matter

Without these wrappers, figures float above the abstract on page 1.

## Citation handling

The PNAS bibliography style is numbered with `sort&compress` (so
`\cite{a,b,c}` may render as `(1-3)` if the three keys are adjacent). The
shared `force_cite` filter rewrites pandoc's `\citet`/`\citep` to plain
`\cite{}` to match.

## Gotchas

- `pnas-new.cls` requires the `algorithm` and `algorithmicx` packages
  which are **not** in a default TeXLive install. The template directory
  bundles `algorithm.sty`, `algorithmic.sty`, `algorithmicx.sty`,
  `algpseudocode.sty` from CTAN to fill the gap.
- The DRAFT watermark is disabled by default (the PNAS class enables it
  at submission). Set `journal.displaywatermark: true` if you actually
  want the watermark on submissions.
