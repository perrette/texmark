import panflute as pf
from pathlib import Path

from texmark.context import BuildContext
from texmark.shared import BOOK_FAMILY_TEMPLATES


def _is_remote_url(url):
    return url.startswith(('http://', 'https://'))


def _is_embed_url(url):
    return url and not _is_remote_url(url) and url.lower().endswith('.md')


def _is_include_link(elem):
    """Return True if elem is a Link with the exact 'include' class and a local .md URL."""
    return (
        isinstance(elem, pf.Link)
        and 'include' in elem.classes
        and _is_embed_url(elem.url)
    )


def _embed_command(doc):
    """Return ``\\include`` for top-level embeds in book-family templates,
    ``\\input`` otherwise.

    Nested embeds always use ``\\input`` (LaTeX forbids nested ``\\include``);
    the body-only embed build passes ``embed_depth=1`` in metadata to signal
    that.
    """
    if doc is None:
        return '\\input'
    if BuildContext.from_doc(doc).embed_depth >= 1:
        return '\\input'
    journal = doc.get_metadata('journal', {}) or {}
    template = journal.get('template') if isinstance(journal, dict) else None
    if template in BOOK_FAMILY_TEMPLATES:
        return '\\include'
    return '\\input'


def _per_chapter_bib(doc):
    """Return True when the active document opts into biblatex per-chapter
    bibliographies (``bibliography_per_chapter: true`` in its YAML)."""
    if doc is None:
        return False
    return bool(doc.get_metadata('bibliography_per_chapter', False))


def _embed_rawblock(cmd, stem, doc):
    """Build the RawBlock LaTeX for one embed.

    Normally just ``\\input{stem}`` / ``\\include{stem}``. When the document
    requested per-chapter bibliographies (Item 18) *and* this is a top-level
    book-family ``\\include`` embed, wrap it in a biblatex ``refsection`` so the
    chapter prints its own References section. Nested embeds (which emit
    ``\\input``) are never wrapped — they live inside their parent's refsection.
    """
    if cmd == '\\include' and _per_chapter_bib(doc):
        text = (
            '\\begin{refsection}\n'
            f'{cmd}{{{stem}}}\n'
            '\\printbibliography[heading=subbibliography]\n'
            '\\end{refsection}\n'
        )
    else:
        text = f'{cmd}{{{stem}}}\n'
    return pf.RawBlock(text, format='latex')


def embed_filter(elem, doc):
    """Rewrite standalone .md embeds to LaTeX ``\\input{stem}`` or
    ``\\include{stem}`` blocks (class-aware via ``embed_depth`` + template)."""
    # _embed_command's inputs (embed_depth, journal.template) are constant
    # for the whole doc, so resolve it once per walk instead of repeating the
    # metadata lookups for every element (~6944 calls on a typical paper).
    cmd = getattr(doc, '_texmark_embed_cmd', None)
    if cmd is None:
        cmd = _embed_command(doc)
        doc._texmark_embed_cmd = cmd

    if isinstance(elem, pf.Figure):
        images = []
        def _gather(e, d):
            if isinstance(e, pf.Image):
                images.append(e)
        elem.walk(_gather)
        if len(images) == 1 and _is_embed_url(images[0].url):
            stem = Path(images[0].url).stem
            return _embed_rawblock(cmd, stem, doc)

    if isinstance(elem, pf.Para):
        children = list(elem.content)
        if len(children) == 1:
            child = children[0]
            if isinstance(child, pf.Image) and _is_embed_url(child.url):
                stem = Path(child.url).stem
                return _embed_rawblock(cmd, stem, doc)
            if _is_include_link(child):
                stem = Path(child.url).stem
                return _embed_rawblock(cmd, stem, doc)


def main(doc=None):
    return pf.run_filter(embed_filter, doc=doc)


if __name__ == '__main__':
    main()
