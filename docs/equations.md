# Numbered and cross-referenced equations

texmark lets you write display equations once, in a form that renders live in
the Markdown preview (VS Code, JetBrains, GitHub — all via KaTeX), and have the
PDF come out properly numbered and cross-referenced.

## The one rule

A class on a display-math block **names the LaTeX outer environment** to wrap it
in. There is no texmark-specific vocabulary to learn — if you know LaTeX's math
environments, you know the classes.

| Markdown | LaTeX | Result |
|---|---|---|
| `$$ x = y $$` | `\[ x = y \]` | unnumbered (default) |
| `$$ x = y $$ {.equation}` | `\begin{equation} … \end{equation}` | one number |
| `$$ … $$ {.align}` | `\begin{align} … \end{align}` | one number per row |
| `$$ … $$ {.gather}` | `\begin{gather} … \end{gather}` | falls out for free |
| `$$ … $$ {#eq:foo}` | `equation` + `\label{eq:foo}` | numbered + referenceable |
| `$$ … $$ {#eq:foo .align}` | `align` + `\label{eq:foo}` | per-row + referenceable |

No class means **no number** — so casual math stays clean and identical in
preview and PDF. A bare label (`{#eq:foo}`, no class) implies `.equation`,
because you only label what you intend to cite, and citing needs a number.

## Cross-references

Reference a labelled equation with a plain Markdown link or a pandoc-style `@`:

```markdown
$$
\begin{aligned}
\boldsymbol{\mathcal{X}} \sim \mathcal{N}(\bar{X}, \Sigma)
\end{aligned}
$$ {#eq:prior}

The prior is given in [](#eq:prior) — equivalently, @eq:prior.
```

Both `[](#eq:prior)` and `@eq:prior` become `\eqref{eq:prior}`, which renders as
a parenthesised, hyperlinked number — `(3)`. (Use `\eqref` rather than `\ref` so
equations read "as in (3)", not "as in 3".)

There is no range syntax: write `Eqs. [](#eq:a)–[](#eq:b)` explicitly.

## Multi-line math and the preview

KaTeX cannot render a bare `&`/`\\` inside `$$…$$` — multi-line math **must** be
wrapped in `aligned` to show up in the preview:

```markdown
$$
\begin{aligned}
a &= b \\
c &= d
\end{aligned}
$$
```

That previews fine and, untagged, compiles to an unnumbered `\[ … \]`.

- For **one number** over the whole block, tag it `{.equation}` (or `{#eq:foo}`).
  The inner `aligned` is kept: `\begin{equation}\begin{aligned}…\end{aligned}\end{equation}`
  — the canonical idiom for a single-numbered aligned equation.
- For **one number per row**, tag it `{.align}`. Here texmark **strips** the
  inner `aligned` so the rows land directly in `align` (otherwise the nesting
  would collapse back to a single number). You keep the preview *and* get
  per-row numbering from the same source. The same unwrapping applies to the
  rest of the alignment family — `flalign`, `alignat`.

This is the only place texmark touches the body; every other environment is
wrapped verbatim.

## Caveats

- **The label shows in the preview.** KaTeX doesn't understand the `{#eq:foo}`
  trailer, so it appears as literal text after the rendered equation in the
  preview. The PDF is unaffected. This is cosmetic and only on labelled blocks.
- **Unknown environments pass through with a warning.** A typo like
  `{.equaton}`, or an inner-only environment used standalone like `{.aligned}`
  (which errors in LaTeX), is emitted as-is and logged — so a build warning
  points you at the mistake.
- **Numbering is LaTeX's.** texmark emits `\label`; the actual numbers come from
  LaTeX's normal two-pass `.aux` resolution. Nothing is counted by texmark, so
  numbering and `\eqref` behave exactly as in hand-written LaTeX.

## See also

- [docs/encoding.md](encoding.md) — Unicode/HTML handling in body and bib text.
- [README](../README.md#numbered-equations) — the short version.
