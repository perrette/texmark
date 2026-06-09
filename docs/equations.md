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
$$

{#eq:prior}

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

## Where to put the trailer (GitHub compatibility)

**Put the `{...}` trailer after a blank line, not stuck to the closing `$$`.**

GitHub renders a `$$…$$` display block only when the closing `$$` ends its line.
If the trailer is glued to it (`$$ {#eq:foo}`), GitHub never sees a valid closing
delimiter and the whole equation falls back to literal text. Keeping the
delimiters clean and dropping the trailer below a blank line lets the equation
render on GitHub *and* in the VS Code preview:

```markdown
$$
\begin{aligned}
\boldsymbol{\mathcal{X}} \sim \mathcal{N}(\bar{X}, \Sigma)
\end{aligned}
$$

{#eq:prior}
where $\bar{X}$ is the weighted ensemble mean …
```

texmark attaches the trailer across **any** whitespace — same line, the next
line, or a blank line — and it may be followed immediately by prose, which stays
in place. So the blank-line form costs you nothing on the texmark side while
making the equation portable.

**Paragraph flow.** The blank line you add before the trailer is only there to
satisfy the `$$` block syntax, so texmark does *not* turn it into a paragraph
break: the equation, its trailer, and the prose on the trailer's line stay in one
paragraph (the equation flows on into the sentence). A new paragraph starts only
where you leave a blank line *after* the trailer's prose — paragraph breaks are
controlled by what comes after the `{...}`, not by the syntactic blank line
before it.

```markdown
$$
\Sigma_{i,j} = \tfrac{1}{M-1}\textstyle\sum_m (X_i^m-\bar X_i)(X_j^m-\bar X_j)
$$

{#eq:cov}
where $\mathcal{L}$ is the localisation kernel.   ← same paragraph as the equation

This sentence starts a new paragraph.             ← blank line above => new paragraph
```

The one residual: GitHub (and the KaTeX preview) still show `{#eq:prior}` as
literal text, since the attribute isn't part of their Markdown. That small leak
is unavoidable while staying in pandoc syntax; the equation itself renders
everywhere, which is the part that matters.

## Caveats

- **The label shows in the preview.** Neither KaTeX (VS Code) nor GitHub
  understands the `{#eq:foo}` trailer, so it appears as literal text near the
  rendered equation. The PDF is unaffected. Cosmetic, and only on labelled
  blocks — see [Where to put the trailer](#where-to-put-the-trailer-github-compatibility).
- **Unknown environments pass through with a warning.** A typo like
  `{.equaton}`, or an inner-only environment used standalone like `{.aligned}`
  (which errors in LaTeX), is emitted as-is and logged — so a build warning
  points you at the mistake.
- **Numbering is LaTeX's.** texmark emits `\label`; the actual numbers come from
  LaTeX's normal two-pass `.aux` resolution. Nothing is counted by texmark, so
  numbering and `\eqref` behave exactly as in hand-written LaTeX.

## See also

- [Encoding](encoding.md) — Unicode/HTML handling in body and bib text.
