import panflute as pf
from pathlib import Path


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


def embed_filter(elem, doc):
    """Rewrite standalone .md image embeds to LaTeX \\input{stem} blocks."""
    if isinstance(elem, pf.Figure):
        images = []
        def _gather(e, d):
            if isinstance(e, pf.Image):
                images.append(e)
        elem.walk(_gather)
        if len(images) == 1 and _is_embed_url(images[0].url):
            stem = Path(images[0].url).stem
            return pf.RawBlock(f'\\input{{{stem}}}\n', format='latex')

    if isinstance(elem, pf.Para):
        children = list(elem.content)
        if len(children) == 1:
            child = children[0]
            if isinstance(child, pf.Image) and _is_embed_url(child.url):
                stem = Path(child.url).stem
                return pf.RawBlock(f'\\input{{{stem}}}\n', format='latex')
            if _is_include_link(child):
                stem = Path(child.url).stem
                return pf.RawBlock(f'\\input{{{stem}}}\n', format='latex')


def main(doc=None):
    return pf.run_filter(embed_filter, doc=doc)


if __name__ == '__main__':
    main()
