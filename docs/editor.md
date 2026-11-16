# Editor setup (VS Code)

texmark works with any text editor. This page describes the VS Code setup the
author uses while writing a thesis with texmark. Other extensions and editors
can do the same jobs; if you find a better setup, please
[open an issue](https://github.com/perrette/texmark/issues) so it can be added
here.

## Citations: Pandoc Citer

[Pandoc Citer](https://marketplace.visualstudio.com/items?itemName=notZaki.pandocciter)
(`notZaki.pandocciter`) completes citation keys after `@`, from the
bibliography named in the YAML front matter (`bibliography: references.bib`),
and shows the reference on hover.

Chapters of a [multi-file project](multi-file.md) usually have no front
matter of their own. Name the bibliography in the workspace settings
(`.vscode/settings.json`) so that completion works there too:

```json
{
  "PandocCiter.DefaultBibs": ["references.bib"],
  "[markdown]": {
    "editor.quickSuggestions": {"other": "on", "comments": "off", "strings": "on"},
    "editor.suggest.showWords": false
  }
}
```

The `[markdown]` part shows the completion list while typing and leaves out
the words of the document from it.

Pandoc Citer also completes the labels of figures, tables, equations and
sections (`@fig:…`, `@tbl:…`, `@eq:…`, `@sec:…`), taken from the `{#…}`
attributes of the current file (and of other files, with the
[patched build](#patched-builds)).

## Track changes: kaicrit

[kaicrit](https://kaijen.github.io/kaicrit/latest/) highlights the
[CriticMarkup](track-changes.md) edits in the editor (deletions, additions,
substitutions, comments), lists them in a side bar, accepts or rejects them
one by one or all at once, and renders them in the Markdown preview
(`Ctrl+Shift+V`). It is installed from the `.vsix` file of its
[GitHub releases](https://github.com/kaijen/kaicrit/releases):

```bash
code --install-extension kaicrit-<version>.vsix
```

A change is accepted or rejected from the links in the tooltip shown when
hovering over it, from a row of links above each change
(`"kaicrit.edit.changeActions": "codeLens"`), or with `Alt+A` / `Alt+R`
with the cursor inside it.

With **Track Changes** on (`Alt+K Alt+T`, the button in the editor title
bar, or the status bar item), edits are recorded as CriticMarkup: deleted
text is wrapped in `{-- … --}`, typed text in `{++ … ++}`, and a replaced
selection becomes `{~~ old ~> new ~~}`. The state is per file.

Without such an extension, VS Code's own Markdown highlighting reads
`~~ ... ~~` as strikethrough and shows the whole of a substitution
`{~~ old ~> new ~~}` struck out, new text included. With kaicrit, the old
text is shown as deleted and the new text as added.

## Markdown preview

`Ctrl+K V` opens VS Code's Markdown preview next to the editor. It renders
equations (KaTeX) and images, follows the editor when scrolling, and, with
kaicrit installed, shows the CriticMarkup edits. Without further extensions,
texmark's own syntax is shown as plain text.

[texmark for VS Code](https://github.com/perrette/texmark-vscode) adds
texmark's syntax to this preview: `{#fig:…}` attributes are shown as small
tags, `@fig:…` references link to their label, and citations are marked.
References are not numbered, since the numbers exist only in the PDF. It is
installed from a `.vsix` file built from its repository:

```bash
git clone https://github.com/perrette/texmark-vscode
cd texmark-vscode
npm install
npm run package
code --install-extension texmark-<version>.vsix
```

Without this extension, the preview's math rendering reads a label written
on the same line as the closing `$$` (`$$ x = y $$ {#eq:foo}`) as part of
the equation and runs on to the next `$$`, so the rest of the file is not
rendered. Writing the label as a paragraph of its own after the equation
avoids this; texmark reads both forms:

```markdown
$$ x = y $$

{#eq:foo}
```

## Patched builds

The author uses patched builds of Pandoc Citer and kaicrit. The fixes are
proposed upstream and are not yet in a release. Each fork has a
`local-build` branch with all of them:

**Pandoc Citer**
([perrette/PandocCiter](https://github.com/perrette/PandocCiter/tree/local-build)):

- Labels with `-`, `.` or `:` (`{#fig:sat-vs-sst}`) are completed in full,
  not cut at the first `-`
  ([#64](https://github.com/notZaki/PandocCiter/pull/64)).
- Choosing a label after `@fig:` replaces what was typed, instead of
  producing `@fig:fig:sat`
  ([#65](https://github.com/notZaki/PandocCiter/pull/65)).
- A new setting, `PandocCiter.CrossRefFiles`, lists glob patterns of
  files whose labels are also offered, so that a chapter can refer to a
  figure of another chapter
  ([#66](https://github.com/notZaki/PandocCiter/pull/66)). In a
  multi-file project:

    ```json
    "PandocCiter.CrossRefFiles": ["*.md"]
    ```

**kaicrit**
([perrette/kaicrit](https://github.com/perrette/kaicrit/tree/local-build)):

- With Track Changes on, typing records one `{++ … ++}` addition for the
  whole word, with the cursor staying at the end, instead of one addition
  per character ([#87](https://github.com/kaijen/kaicrit/pull/87)).
- The Track Changes button in the editor title bar shows whether it is on
  or off ([#88](https://github.com/kaijen/kaicrit/pull/88)).

Each is built and installed like this (shown for Pandoc Citer):

```bash
git clone -b local-build https://github.com/perrette/PandocCiter
cd PandocCiter
npm install
npx @vscode/vsce package
code --install-extension pandocciter-<version>.vsix
```

## Recommending the extensions in a project

A `.vscode/extensions.json` file in the project makes VS Code offer to
install the extensions when the folder is opened. kaicrit is not on the
Marketplace, so only Pandoc Citer can be listed:

```json
{
  "recommendations": ["notZaki.pandocciter"]
}
```

## Building and viewing the PDF

Run the [live preview](live-preview.md) in the integrated terminal:

```bash
texmark main.md --pdf --watch --progressive
```

Every save (`Ctrl+S`) rebuilds the PDF. Open the PDF in a viewer that reloads
the file when it changes; the author uses GNOME Papers, next to the editor
window.
