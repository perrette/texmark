"""texmark-crossref-labels: references to labelled objects within one document.

Labels are defined by the figure, table, heading and equation handling
(``{#fig:x}``, ``{#tbl:x}``, ``{#sec:x}``, ``{#eq:x}``, ``{#lst:x}``); this
filter writes the *references* to them, using pandoc-crossref's syntax.

A citation whose keys **all** start with one of the prefixes ``fig:``,
``eq:``, ``tbl:``, ``sec:``, ``lst:`` is not a bibliography citation but a
reference, and becomes raw LaTeX (``~`` is a non-breaking space). By default
it is the bare number, so the author writes the noun::

    Figure @fig:a  or  [@fig:a]     ->  Figure \\ref{fig:a}
    @eq:a                           ->  \\eqref{eq:a}               (as "(3)")
    [@fig:a; @fig:b]                ->  \\ref{fig:a} and~\\ref{fig:b}
    [@fig:a; @fig:b; @fig:c]        ->  \\ref{fig:a}, \\ref{fig:b} and~\\ref{fig:c}

Prefix words are opt-in, from the ``crossref`` mapping in the front matter (or
a journal's ``crossref`` entry in ``texmark.journals.JOURNALS``, none by
default; the front matter wins)::

    crossref: {fig: "Fig.", figs: "Figs.", eq: "Eq.", eqs: "Eqs.",
               tbl: "Table", tbls: "Tables", sec: "Sect.", secs: "Sects.",
               lst: "Listing", lsts: "Listings"}

With ``fig`` and ``figs`` set, ``@fig:a`` gives ``Fig.~\\ref{fig:a}`` and
``[@fig:a; @fig:b]`` gives ``Figs.~\\ref{fig:a} and~\\ref{fig:b}``. Mixed kinds
in one bracket give one run per kind, joined the same way. A bracket that
mixes in a real citation key is left alone, as a citation. Keys without a word
configured give bare numbers.

A same-document *link* ``[#](#id)`` (or ``[](#id)``) always gives the bare
``\\ref``/``\\eqref`` -- the link text is where the author writes the words.
Links to other documents (``other.md#id``) belong to ``texmark-crossref``.
"""
from __future__ import annotations

import panflute as pf

# Label prefix -> (LaTeX command for the number, key of the singular word,
# key of the plural word). Equations take ``\eqref`` (parenthesised number).
_KINDS = {
    "fig": ("ref", "fig", "figs"),
    "eq": ("eqref", "eq", "eqs"),
    "tbl": ("ref", "tbl", "tbls"),
    "sec": ("ref", "sec", "secs"),
    "lst": ("ref", "lst", "lsts"),
}

# No words by default: a reference is the bare number (``\\ref``/``\\eqref``),
# the author writing the noun ("Figure @fig:a"). Words are opt-in.
DEFAULT_PREFIXES = {key: "" for _kind in _KINDS.values() for key in _kind[1:]}


def label_kind(identifier):
    """The kind (``fig``/``eq``/``tbl``/``sec``/``lst``) of a label such as
    ``fig:x``, or ``None`` if it has no cross-reference prefix (a real
    citation key, a heading slug)."""
    prefix, sep, rest = identifier.partition(":")
    return prefix if sep and rest and prefix in _KINDS else None


def _ref(identifier):
    return f"\\{_KINDS[label_kind(identifier)][0]}{{{identifier}}}"


def _join(items, conjunction):
    """``a``; ``a and b``; ``a, b and c`` (``conjunction`` is the ``and``)."""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + conjunction + items[-1]


def _runs(keys):
    """Split keys into runs of consecutive keys of the same kind."""
    runs = []
    for key in keys:
        if runs and label_kind(runs[-1][0]) == label_kind(key):
            runs[-1].append(key)
        else:
            runs.append([key])
    return runs


def format_references(keys, prefixes):
    """LaTeX for a list of labels (all with a cross-reference prefix)."""
    parts = []
    for run in _runs(keys):
        _cmd, singular, plural = _KINDS[label_kind(run[0])]
        word = prefixes[singular if len(run) == 1 else plural]
        text = _join([_ref(k) for k in run], " and~")
        parts.append(f"{word}~{text}" if word else text)
    return _join(parts, " and ")


class CrossrefLabelsFilter:
    """Rewrite same-document references (``@fig:x``, ``[#](#fig:x)``, ...).

    ``prefixes`` are the journal's default words, overriding
    ``DEFAULT_PREFIXES`` and overridden by the document's ``crossref`` mapping.
    """

    def __init__(self, prefixes=None):
        self.journal_prefixes = dict(prefixes or {})
        self.prefixes = {**DEFAULT_PREFIXES, **self.journal_prefixes}

    def prepare(self, doc):
        user = doc.get_metadata("crossref", None)
        user = user if isinstance(user, dict) else {}
        self.prefixes = {
            **DEFAULT_PREFIXES,
            **self.journal_prefixes,
            **{k: str(v) for k, v in user.items() if k in DEFAULT_PREFIXES},
        }

    def action(self, elem, doc):
        if isinstance(elem, pf.Cite):
            keys = [c.id for c in elem.citations]
            if not keys or not all(label_kind(k) for k in keys):
                return None
            # Prose written inside the bracket ([see @fig:a, left panel]).
            before = list(elem.citations[0].prefix)
            after = list(elem.citations[-1].suffix)
            ref = pf.RawInline(format_references(keys, self.prefixes), format="latex")
            if before or after:
                return pf.Span(*before, ref, *after)
            return ref
        if isinstance(elem, pf.Link):
            url = elem.url or ""
            # Only a lone ``#`` (the marker that stays clickable on GitHub) or
            # nothing as link text; anything else is left for pandoc to render
            # as ``\hyperref[label]{text}`` with its text kept verbatim.
            if url.startswith("#") and pf.stringify(elem).strip() in ("", "#"):
                label = url[1:]
                cmd = _KINDS[label_kind(label)][0] if label_kind(label) else "ref"
                return pf.RawInline(f"\\{cmd}{{{label}}}", format="latex")
        return None


crossref_labels_filter = CrossrefLabelsFilter()


def main(doc=None):
    return pf.run_filter(
        crossref_labels_filter.action,
        prepare=crossref_labels_filter.prepare,
        doc=doc,
    )


if __name__ == "__main__":
    main()
