#!/usr/bin/env python3

import sys
import json
import panflute as pf
from texmark.logs import logger
from texmark.shared import filters, default_filter
from texmark.shared import JournalFilter, filters, logger, Processor
from texmark.sectiontracker import SectionProcessor

copernicus_filter = JournalFilter(
        processors = [
            SectionProcessor(
                extract_sections=['abstract', 'appendix', 'acknowledgements', 'author-contributions', 'competing-interests'],
                sections_map={
                    'author-contributions': 'authorcontribution',
                    'competing-interests': 'competinginterests',
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


science_filter = JournalFilter(
        processors = [
            SectionProcessor(
                extract_sections=['abstract', 'appendix', 'acknowledgements', 'author-contributions',
                                  'competing-interests', 'methods', 'materials-and-methods', 'supplementary-material'],
                sections_map={
                    'author-contributions': 'authorcontribution',
                    'competing-interests': 'competinginterests',
                    'supplementary-material': 'appendix',
                    'methods': 'materialsandmethods',
                    'materials-and-methods': 'materialsandmethods',
                },
                remap_command_sections={
                    'introduction': r'\introduction',
                    'conclusions': r'\conclusions'
                }
            ),
            Processor(
                action=force_cite,
            )
        ])

filters['science'] = [science_filter]

def run_filters(doc):

    if doc is not None:
        journal = doc.get_metadata('journal')
    else:
        journal = {'template': 'default'}

    logger.warning(f'doc:: {doc}')
    logger.warning(f'journal:: {journal}')
    logger.warning(f'filters:: {filters.keys()}')
    logger.warning(f'Journal template: {journal.get("template")}')
    filters_ = filters.get(journal.get("template"), [default_filter])

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