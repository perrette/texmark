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

Without such an extension, VS Code's own Markdown highlighting reads
`~~ ... ~~` as strikethrough and shows the whole of a substitution
`{~~ old ~> new ~~}` struck out, new text included. With kaicrit, the old
text is shown as deleted and the new text as added.

## Building and viewing the PDF

Run the [live preview](live-preview.md) in the integrated terminal:

```bash
texmark main.md --pdf --watch --progressive
```

Every save (`Ctrl+S`) rebuilds the PDF. Open the PDF in a viewer that reloads
the file when it changes; the author uses GNOME Papers, next to the editor
window.
