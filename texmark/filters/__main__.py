#!/usr/bin/env python3

import sys
import json
import re
from pathlib import Path
import importlib
import panflute as pf
from texmark.logs import logger
from texmark.shared import filters
from texmark.sectiontracker import SectionFilter
from texmark.filters.tabular import table_to_latex

def strip_leading_slash(elem, doc):
    if hasattr(elem, 'url'):
        if elem.url.startswith('/'):
            # Remove leading slash to make it repo-root relative (like GitHub)
            elem.url = elem.url.lstrip('/')

def tag_figures(elem, doc):
    if isinstance(elem, pf.Figure):
        # if it does not already exist, add an identifier to the figure so that it can be referenced
        # in the text using \ref{fig:figure-id}
        # use the content image url as the identifier, e.g. /image/figure.png -> fig:figure
        if not elem.identifier:
            # Generate a unique identifier for the figure
            image = elem.content[0].content[0]
            tag = f'fig:{Path(image.url).stem}'
            logger.info(fr"Tagging figure: {tag}")
            elem.identifier = tag
    return elem


ATTR_RE = re.compile(r'\s*\{([^}]+)\}\s*$')

def parse_attr_string(attr_string):
    identifier = ''
    classes = []
    attributes = {}
    for token in attr_string.split():
        if token.startswith('#'):
            identifier = token[1:]
        elif token.startswith('.'):
            classes.append(token[1:])
        elif '=' in token:
            key, val = token.split('=', 1)
            attributes[key] = val
    return identifier, classes, attributes

def extract_table_identifier(elem, doc):
    if not isinstance(elem, pf.Table):
        return

    cap = elem.caption
    if not cap or not cap.content:
        return

    # at the time of writing, the caption is ListContainer(Plain(...))
    if not (
        cap.content
        and len(cap.content) == 1
        and isinstance(cap.content[0], pf.Plain)
    ):
        logger.warning(f"Caption content is not a Plain block: {cap.content}")
        return

    inlines = cap.content[0].content

    last = inlines[-1]
    if not isinstance(last, pf.Str):
        return

    last_text = pf.stringify(last).strip()
    match = ATTR_RE.search(last_text)
    if not match:
        return

    attr_string = match.group(1)
    identifier, classes, attributes = parse_attr_string(attr_string)

    cap.content[:] = [pf.Plain(*inlines[:-1])]

    if identifier:
        elem.identifier = identifier
    if classes:
        elem.classes.extend(classes)
    if attributes:
        elem.attributes.update(attributes)


def stringify_captions(elem, doc):

    if isinstance(elem, (pf.Table)):
        extract_table_identifier(elem, doc)

    if isinstance(elem, (pf.Figure, pf.Table)):
        # Safely extract caption
        if elem.caption:
            caption_text = pf.convert_text(elem.caption.content,
                input_format='panflute',
                output_format='latex',
                extra_args=['--natbib']
            )

            # Science template: make the first sentence bold
            if doc.get_metadata('journal', {}).get("template") == "science":
                caption_parts = caption_text.split(".")
                caption_parts[0] = r"\textbf{" + caption_parts[0] + r"}"
                caption_text = ".".join(caption_parts)

            elem.caption.content = [pf.RawBlock(caption_text, format='latex')]


def apply_figure_defaults(elem, doc):
    """Apply global figure-width and figure-span metadata to figures.

    - `figure-width` (default `100%`) sets the default image width when none is
      given on the figure itself. Percent values are interpreted by pandoc as a
      fraction of `\\linewidth`, which inside `figure*` automatically expands
      to the full text width.
    - `figure-span` (default `column`) — when set to `full`, wrap the figure in
      a `figure*` environment so it spans both columns in two-column layouts.
    """
    if not isinstance(elem, pf.Figure):
        return

    target = elem.content[0].content[0]
    if "width" not in target.attributes:
        target.attributes['width'] = doc.get_metadata('figure-width', '100%')

    if doc.get_metadata('figure-span', 'column') == 'full':
        latex = pf.convert_text(
            elem,
            input_format='panflute',
            output_format='latex',
            extra_args=['--natbib'],
        )
        latex = latex.replace(r'\begin{figure}', r'\begin{figure*}')
        latex = latex.replace(r'\end{figure}', r'\end{figure*}')
        return pf.RawBlock(latex, format='latex')

basic_filters = [strip_leading_slash, stringify_captions, tag_figures, apply_figure_defaults, table_to_latex ]

default_filters = basic_filters

si_sections = ["appendix", "supplementary-material", "supplementary-information"]
method_sections = ["methods", "materials-and-methods", "methodology"]


copernicus_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=['abstract', 'acknowledgements', 'author-contributions', 'competing-interests'] + si_sections,
        remap_command_sections={
            'introduction': r'\introduction',
            'conclusions': r'\conclusions'
        },
        sections_map={
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

for journal in ["copernicus", "cp", "esd"]:
    filters[journal] = copernicus_filters


def force_cite(elem, doc):
    if isinstance(elem, pf.Cite):
        keys = [c.id for c in elem.citations]
        key_str = ",".join(keys)
        # Build as raw LaTeX \cite{}
        return pf.RawInline(f'\\cite{{{key_str}}}', format='latex')

def header_to_unnumbered(elem, doc):
    if isinstance(elem, pf.Header):
        # Convert header to raw LaTeX \section*{...}
        level = elem.level
        content = pf.stringify(elem)
        latex_cmd = f'\\{"sub" * (level - 1)}section*{{{content}}}'
        return pf.RawBlock(latex_cmd, format='latex')

def header_to_paragraph(elem, doc):
    if isinstance(elem, pf.Header):
        # Convert header to raw LaTeX \section*{...}
        level = elem.level
        content = pf.stringify(elem)
        latex_cmd = f'\\paragraph*{{{content+"."}}}'
        return pf.RawBlock(latex_cmd, format='latex')


science_filters = [
    *basic_filters,
    force_cite,
    SectionFilter(
        extract_sections=['abstract', 'acknowledgements', 'author-contributions',
                            'competing-interests', 'methods', 'materials-and-methods'] + si_sections,
        sections_map={
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'materialandmethods' for section in method_sections},
            **{section: 'appendix' for section in si_sections},
        },
    ),
    header_to_paragraph,
        ]

filters['science'] = science_filters


ametsoc_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=[
            'abstract', 'acknowledgements', 'acknowledgments',
            'significance', 'significance-statement', 'capsule',
            'data-availability', 'data-availability-statement',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'significance-statement': 'significance',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

for journal in ["ametsoc", "amsoc", "jclim", "jas", "mwr", "jamc", "jhm", "jpo", "jtech", "waf", "bams"]:
    filters[journal] = ametsoc_filters


arxiv_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions', 'competing-interests',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

filters['arxiv'] = arxiv_filters
filters['preprint'] = arxiv_filters


elsarticle_filters = [
    *basic_filters,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords', 'highlights',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions', 'credit', 'competing-interests',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'credit': 'authorcontribution',
            'competing-interests': 'competinginterests',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

filters['elsarticle'] = elsarticle_filters
filters['elsevier'] = elsarticle_filters


def run_filters(doc):

    if doc is not None:
        journal = doc.get_metadata('journal')
    else:
        logger.warning(f'doc is None')
        journal = {'template': 'default'}

    if doc.get_metadata('filters_module'):
        filters_module = doc.get_metadata('filters_module')
        logger.info(f"Loading filters module: {filters_module}")
        importlib.import_module(filters_module)


    if journal.get("template") is None:
        logger.warning(f'doc is None')

    filters_ = filters.get(journal.get("template"))
    if filters_ is None:
        logger.warning(f'No filters found for journal template: {journal.get("template")}. Using default filter.')
        filters_ = default_filters


    for filter in filters_:
        logger.info(f'Running filter: {filter} on {doc}')
        doc = pf.run_filter(action=filter.action if hasattr(filter, 'action') else filter,
                   prepare=filter.prepare if hasattr(filter, 'prepare') else None,
                   finalize=filter.finalize if hasattr(filter, 'finalize') else None,
                   doc=doc)
        assert isinstance(doc, pf.Doc), f"Filter {filter} did not return a valid doc object"

    return doc


def main(doc=None):
    doc = pf.load(sys.stdin)
    doc = run_filters(doc)
    return pf.dump(doc)


if __name__ == '__main__':
    main()