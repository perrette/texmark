# To do

Open design questions and known limitations. Bugs are fixed as they are found;
the items here need a decision before any code is written.

## Cross-reference prefix words (issue #7, PR #10)

The bug part of #7 (several keys in one bracket, `@lst:`) is fixed on main.
PR #10 also proposes opt-in words before the number, set in the front matter:

```yaml
crossref: {fig: "Fig.", figs: "Figs.", eq: "Eq.", eqs: "Eqs.", ...}
```

so that `@fig:a` gives "Fig. 1" and `[@fig:a; @fig:b]` gives "Figs. 1 and 2".
Rendering plain text (`Fig.~\ref{...}`) rather than using `cleveref` keeps it
working with journal classes that clash with or forbid `cleveref`.

Questions to settle first:

- **Sentence-start capitalisation.** Copernicus, for example, wants "Fig." in
  running text and "Figure" at the start of a sentence. pandoc-crossref uses a
  capitalised key (`@Fig:a`) for this. PR #10 has no equivalent.
- **Language.** "and" and the words are hard-coded in English. Options: a
  `lang`-dependent default table, or a conjunction key alongside the words.
- **Journal defaults.** PR #10 adds an optional `crossref` entry to
  `texmark.journals.JOURNALS` so a journal can set default words; no journal
  uses it. Only add it once a journal needs it.
- **Key name.** `crossref:` is close to the existing `texmark-crossref` filter,
  which handles references between documents.
- **Prose between keys.** In `[see @fig:a, left; @fig:b, right]`, only the text
  before the first key and after the last key is kept.

## Metadata

- **Math and markup in `title` / `abstract`.** Front-matter values are
  converted to plain text before reaching the templates, so `$\alpha$` becomes
  a bare `\alpha` (which breaks the build) and `**bold**` loses its markup.
  Affects all templates. Fixing it means rendering metadata strings through
  pandoc to LaTeX, which changes what every template receives.
- **`journal:` that is neither a string nor a mapping** (a list, a number)
  still raises `AttributeError`.

## Templates

- **natbib options in the default template.** The default template always
  loads `natbib`; plain `packages: [natbib]` is now skipped, but a raw
  `\usepackage[numbers]{natbib}` in `packages` still gives an "Option clash".
  No template handles option-bearing duplicates. Options: load natbib only
  if `packages` does not, or a `natbiboptions` key.
- **science: data availability from a markdown section.** The science journal
  config does not list `data-availability` in its `extract_sections`, so the
  statement can only come from the YAML front matter, not from a
  `# Data availability` section.

## Author roles (issue #2, done)

`corresponding` and `equalcontrib` per-author keys are implemented. Left open:

- `equalcontrib` is rendered only by copernicus, springernature, pnas and
  science, which have a native mechanism. Other templates (arxiv, elsarticle,
  agujournal, ametsoc, book-family) would need a symbol and wording choice.
- springernature: `\affil*` (the asterisk on an affiliation label) stays on the
  first affiliation instead of following the corresponding author.
- science: with several corresponding authors the line reads
  "Corresponding authors. Email: a, b"; check against Science's guidelines.
