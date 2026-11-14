# Track changes

texmark reads [CriticMarkup](https://criticmarkup.com), the Markdown notation
for edits and comments, and typesets it with the LaTeX
[`changes`](https://ctan.org/pkg/changes) package: added text in colour,
deleted text struck out, comments numbered in the text.

## Notation

| Markdown | Meaning | LaTeX |
| - | - | - |
| `{++ new text ++}` | addition | `\added{new text}` |
| `{-- old text --}` | deletion | `\deleted{old text}` |
| `{~~ old ~> new ~~}` | substitution | `\deleted{old}\added{new}` |
| `{== text ==}` | highlight | `\highlight{text}` |
| `{>> remark <<}` | comment | `\comment{remark}` |
| `{++ new ++}{>> why <<}` | addition with a comment | `\added[comment={why}]{new}` |

A comment placed directly after another mark (spaces allowed) becomes the
`comment` option of that change. Elsewhere it is a comment of its own.

The text inside a mark is read as Markdown, so citations, cross-references,
emphasis, math, links and footnotes work inside it:

```markdown
The rate rose {++ to more than 4 mm/yr [@smith2020] ++}{>> 10 Nov: new estimate <<}.
```

Rules:

- A mark does not continue across a blank line. Use one mark per paragraph.
- A mark can cover a heading or list items; each line is marked inside its
  heading or item marker:

  ```markdown
  {++ ## Results
  - first finding
  - second finding ++}
  ```

- Marks in code (inline, fenced or indented), math, raw LaTeX and the YAML
  front matter are left as written, so the notation can be shown in code.
- A footnote inside a mark is typeset after the change (LaTeX cannot place a
  footnote inside struck-out text).

## The `changes` option

```yaml
changes: auto     # default
```

| Value | Effect |
| - | - |
| `auto` | on when the document contains a CriticMarkup mark, off otherwise |
| `true` | changes shown (colours, strike-out, comments) |
| `false` | changes accepted: added and highlighted text plain, deleted text and comments removed (with a heading, list item or paragraph left empty); the `changes` package is not loaded |

In a [multi-file project](multi-file.md) the option is read from the master
file only, and `auto` looks at the master file and its chapters. Chapters
share the master's preamble, so a `changes:` key in a chapter is ignored.

## Other notations

With the option on, texmark also reads two notations that other Markdown
tools use for changes:

- GFM strike-out `~~old~~` as a deletion;
- the HTML pair `<ins>new</ins>` / `<del>old</del>` (which GitHub renders) as
  an addition / deletion.

With the option off, `~~old~~` is struck out (`\sout{old}`, from the `ulem`
package, loaded when the document uses strike-out) and the HTML tags are
dropped.

The spans that CriticMarkup is turned into can also be written directly:
`[new]{.added}`, `[old]{.deleted}`, `[text]{.highlight}`, `[remark]{.comment}`,
with an optional `comment="..."` attribute.

## Styling

texmark loads the package with `commandnameprefix=ifneeded` and writes the
commands as `\chadded`, `\chdeleted`, `\chhighlight` and `\chcomment`. These
point to the package's `\added`, `\deleted`, ... and keep working when
another package (for example `comment`) already defines one of those names.

The markup is set with the package's own commands in the
[preamble](preamble.md), for example:

```yaml
preamble: |
  \setaddedmarkup{\textcolor{blue}{#1}}
  \setdeletedmarkup{\textcolor{gray}{\sout{#1}}}
```

See the `changes` package manual for authors (`\definechangesauthor`), the
list of changes (`\listofchanges`) and the markup options.
