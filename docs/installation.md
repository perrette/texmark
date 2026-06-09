# Installation

```bash
pip install texmark
```

## External dependencies

texmark itself is pure Python, but it shells out to a few external tools to
produce the final PDF.

- **pandoc** — the markdown → tex engine. The easiest install is
  `pip install pypandoc_binary`, which ships the pandoc binary as a PyPI
  wheel (no system package manager, no sudo, same on Linux/macOS/Windows,
  recent pandoc 3.x). If you'd rather have a single shared install across
  venvs, use your system package manager instead (see below) — texmark
  picks up either.
- **A LaTeX distribution** providing `pdflatex`, `bibtex`, and `latexmk`
  (texmark's default driver) plus the standard package set (`hyperref`,
  `natbib`, `amsmath`, `graphicx`, `geometry`, `microtype`, `booktabs`,
  `caption`, `mathptmx`, `newtxtext`, `newtxmath`, `apacite`,
  `draftwatermark`, `mdframed`, `tikz`, `xcolor`, `appendix`, `lineno`,
  `epstopdf`, …). Optionally `tectonic` as a single-binary alternative
  (see [Build backends](build-backends.md)).

On Debian / Ubuntu:

```bash
sudo apt install pandoc \
    texlive-latex-extra texlive-bibtex-extra \
    texlive-publishers texlive-fonts-extra
```

…or just `texlive-full` for the easy answer.

On macOS (Homebrew):

```bash
brew install pandoc
brew install --cask mactex     # or basictex + tlmgr install <packages>
```

A handful of LaTeX packages that aren't in TeX Live's smaller installs
(notably `trackchanges`, `algorithm` / `algorithmicx`, `jabbrv`) are
**bundled with texmark** under `texmark/templates/<journal>/` and copied
into the build directory automatically, so you don't need to install them
separately.
