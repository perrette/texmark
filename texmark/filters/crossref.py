"""texmark-crossref: rewrite cross-document markdown links to \\ref + emit xr_preamble.

Companions are sibling documents with their own compiled .tex/.pdf. To make
references between them resolve, LaTeX needs xr-hyper's ``\\externaldocument``
mechanism in the preamble and ``\\ref{<other-stem>:<label>}`` at the call site.

This filter:

  * Rewrites ``[text](other.md#label)`` Link nodes into
    ``\\ref{<other-stem>:<label>}`` when ``<other-stem>`` is a known peer
    (companion or sibling embed) of the active document.
  * Emits a ``xr_preamble`` string into doc metadata for every known peer,
    of the form ``\\usepackage{xr-hyper}\\n\\externaldocument[<stem>:]{<stem>}``.
    Templates render this just before ``\\begin{document}``.

Peers are advertised through metadata set by build.py:
``crossref_companion_stems``, ``crossref_embed_stems``, ``crossref_own_stem``.
"""

from __future__ import annotations

import re
from pathlib import Path

import panflute as pf


_LINK_RE = re.compile(r"^(?P<path>[^#?]*\.md)#(?P<label>.+)$", re.IGNORECASE)


class CrossrefFilter:
    def __init__(self):
        self._reset()

    def _reset(self):
        self.own_stem = ""
        self.known_stems: set[str] = set()
        # Ordered list of stems to emit \externaldocument for.
        self.xr_targets: list[str] = []

    @staticmethod
    def _as_list(value):
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        return list(value)

    def prepare(self, doc):
        self._reset()
        self.own_stem = doc.get_metadata("crossref_own_stem", "") or ""
        comp = self._as_list(doc.get_metadata("crossref_companion_stems", []))
        emb = self._as_list(doc.get_metadata("crossref_embed_stems", []))

        seen: set[str] = set()
        for stem in comp + emb:
            if not stem or stem == self.own_stem or stem in seen:
                continue
            self.xr_targets.append(stem)
            seen.add(stem)
        self.known_stems = set(self.xr_targets)

    def action(self, elem, doc):
        if not isinstance(elem, pf.Link):
            return None
        match = _LINK_RE.match(elem.url or "")
        if not match:
            return None
        stem = Path(match.group("path")).stem
        if stem not in self.known_stems:
            return None
        label = match.group("label")
        return pf.RawInline(f"\\ref{{{stem}:{label}}}", format="latex")

    def finalize(self, doc):
        if not self.xr_targets:
            return
        lines = ["\\usepackage{xr-hyper}"]
        for stem in self.xr_targets:
            lines.append(f"\\externaldocument[{stem}:]{{{stem}}}")
        doc.metadata["xr_preamble"] = pf.MetaString("\n".join(lines) + "\n")


crossref_filter = CrossrefFilter()


def main(doc=None):
    return pf.run_filter(
        crossref_filter.action,
        prepare=crossref_filter.prepare,
        finalize=crossref_filter.finalize,
        doc=doc,
    )


if __name__ == "__main__":
    main()
