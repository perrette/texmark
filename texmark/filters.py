#!/usr/bin/env python3

import sys
import json
import importlib
import panflute as pf
from texmark.logs import logger
from texmark.shared import filters, default_filter
from texmark.shared import JournalFilter, filters, logger, Processor
from texmark.sectiontracker import SectionProcessor

si_sections = ["appendix", "supplementary-material", "supplementary-information"]
method_sections = ["methods", "materials-and-methods", "methodology"]

copernicus_filter = JournalFilter(
        processors = [
            SectionProcessor(
                extract_sections=['abstract', 'acknowledgements', 'author-contributions', 'competing-interests'] + si_sections,
                sections_map={
                    'author-contributions': 'authorcontribution',
                    'competing-interests': 'competinginterests',
                    **{section: 'appendix' for section in si_sections},
                },
                remap_command_sections={
                    'introduction': r'\introduction',
                    'conclusions': r'\conclusions'
                }
            )
        ])

for journal in ["copernicus", "cp", "esd"]:
    filters[journal] = [copernicus_filter]


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


science_filter = JournalFilter(
        processors = [
            SectionProcessor(
                extract_sections=['abstract', 'acknowledgements', 'author-contributions',
                                  'competing-interests', 'methods', 'materials-and-methods'] + si_sections,
                sections_map={
                    'author-contributions': 'authorcontribution',
                    'competing-interests': 'competinginterests',
                    **{section: 'materialandmethods' for section in method_sections},
                    **{section: 'appendix' for section in si_sections},
                },
                remap_command_sections={
                    # 'introduction': r'\section*{Introduction}',
                }
            ),
            force_cite,
            header_to_paragraph,
        ])

filters['science'] = [science_filter]


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
        filters_ = [default_filter]

    for filter in filters_:
        doc = pf.run_filter(action=filter.action,
                   prepare=filter.prepare,
                   finalize=filter.finalize, doc=doc)

    return doc


def main(doc=None):
    doc = pf.load(sys.stdin)
    doc = run_filters(doc)
    return pf.dump(doc)


if __name__ == '__main__':
    main()