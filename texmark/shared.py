import sys
import panflute as pf
from panflute import Image, Table
from texmark.logs import logger

def _run_action(action, elem, doc):
    result = action(elem, doc)
    if result is None:
        return elem
    return result

class Filter:
    def __init__(self, action=None, prepare=None, finalize=None):
        self._action = action
        self._prepare = prepare
        self._finalize = finalize

    def action(self, elem, doc):
        if self._action:
            return _run_action(self._action, elem, doc)
        return elem

    def prepare(self, doc):
        if self._prepare:
            self._prepare(doc)

    def finalize(self, doc):
        if self._finalize:
            self._finalize(doc)

filters = {}

# Templates whose document class is book-family (book, report, memoir,
# classicthesis). Top-level embeds in these templates emit ``\include{stem}``
# so ``\includeonly{}`` can scope them; nested embeds and article-class
# templates emit ``\input{stem}`` instead (LaTeX forbids nested ``\include``).
# Future items (16 classicthesis) extend this set.
BOOK_FAMILY_TEMPLATES = {"book", "report", "memoir"}