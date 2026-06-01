import panflute as pf
from pathlib import Path


def _is_remote_url(url):
    return url.startswith(('http://', 'https://'))


def _is_embed_url(url):
    return url and not _is_remote_url(url) and url.lower().endswith('.md')


def embed_filter(elem, doc):
    """Rewrite standalone .md image embeds to LaTeX \\input{stem} blocks."""
    if isinstance(elem, pf.Figure):
        images = [e for e in elem.walk() if isinstance(e, pf.Image)]
        if len(images) == 1 and _is_embed_url(images[0].url):
            stem = Path(images[0].url).stem
            return pf.RawBlock(f'\\input{{{stem}}}\n', format='latex')

    if isinstance(elem, pf.Para):
        children = list(elem.content)
        if (len(children) == 1
                and isinstance(children[0], pf.Image)
                and _is_embed_url(children[0].url)):
            stem = Path(children[0].url).stem
            return pf.RawBlock(f'\\input{{{stem}}}\n', format='latex')


def main(doc=None):
    return pf.run_filter(embed_filter, doc=doc)


if __name__ == '__main__':
    main()
