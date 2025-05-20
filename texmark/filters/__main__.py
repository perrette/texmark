#!/usr/bin/env python3

import sys
import json
from pathlib import Path
import importlib
import panflute as pf
from texmark.logs import logger
from texmark.shared import filters
from texmark.sectiontracker import SectionFilter


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
            logger.warning(f"Tagging figure: {elem}")
            image = elem.content[0].content[0]
            elem.identifier = f'fig:{Path(image.url).stem}'
    return elem

def figure_width_100pct(elem, doc):
    """Set figure width to 100%"""
    if isinstance(elem, pf.Figure):
        # Set width to 100%
        target = elem.content[0].content[0]
        if "width" not in target.attributes:
            target.attributes['width'] = '100%'
    return elem

basic_filters = [strip_leading_slash, tag_figures, figure_width_100pct]

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
    header_to_paragraph,
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
        ]

filters['science'] = science_filters


def run_filters(doc):

    if doc is not None:
        journal = doc.get_metadata('journal')
    else:
        logger.warning(f'doc is None')
        journal = {'template': 'default'}

    if doc.get_metadata('filters_module'):
        filters_module = doc.get_metadata('filters_module')
        logger.warning(f"Loading filters module: {filters_module}")
        importlib.import_module(filters_module)


    if journal.get("template") is None:
        logger.warning(f'doc is None')

    filters_ = filters.get(journal.get("template"))
    if filters_ is None:
        logger.warning(f'No filters found for journal template: {journal.get("template")}. Using default filter.')
        filters_ = default_filters


    for filter in filters_:
        logger.warning(f'Running filter: {filter} on {doc}')
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