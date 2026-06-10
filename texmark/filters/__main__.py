#!/usr/bin/env python3
"""Console entry point for the ``texmark-journal`` pandoc filter.

The filter implementations live in ``texmark.filters.images``,
``texmark.filters.figures`` and friends; the journal registry and
``run_filters`` live in ``texmark.journals``.
"""

import sys

import panflute as pf

from texmark.journals import run_filters


def main(doc=None):
    doc = pf.load(sys.stdin)
    doc = run_filters(doc)
    return pf.dump(doc)


if __name__ == '__main__':
    main()
