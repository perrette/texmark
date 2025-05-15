#!/usr/bin/env python3

import sys
import json
import panflute as pf
from texmark.logs import logger
from texmark.shared import filters, default_filter
import texmark.copernicus

# filters["copernicus"] = [copernicus_filter]
def run_filters(doc):

    if doc is not None:
        journal = doc.get_metadata('journal')
    else:
        journal = {'family': 'default'}

    logger.warning(f'doc:: {doc}')
    logger.warning(f'journal:: {journal}')
    logger.warning(f'filters:: {filters.keys()}')
    logger.warning(f'Journal family: {journal.get("family")}')
    filters_ = filters.get(journal.get("family"), [default_filter])

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