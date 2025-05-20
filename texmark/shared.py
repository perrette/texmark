import sys
import panflute as pf
from panflute import Image, Table
from texmark.logs import logger

def _run_action(action, elem, doc):
    result = action(elem, doc)
    if result is None:
        return elem
    return result

class Processor:
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

class JournalFilter:
    def __init__(self, processors=None):
        self.processors = processors or []

    def prepare(self, doc):
        for processor in self.processors:
            if hasattr(processor, "prepare"):
                processor.prepare(doc)

    def action(self, elem, doc):

        if hasattr(elem, 'url'):
            if elem.url.startswith('/'):
                # Remove leading slash to make it repo-root relative (like GitHub)
                elem.url = elem.url.lstrip('/')

        if isinstance(elem, Image):
            elem = _run_action(self.transform_figure, elem, doc)

        elif isinstance(elem, Table):
            elem = _run_action(self.transform_table, elem, doc)

        # if isinstance(elem, Header):
        #     return self.transform_header(elem, doc)
        for processor in self.processors:
            elem = _run_action(processor if callable(processor) else processor.action, elem, doc)

        return elem

    def finalize(self, doc):
        for processor in self.processors:
            if hasattr(processor, "finalize"):
                processor.finalize(doc)
        return

    # def transform_header(self, elem, doc):
    #     pass

    def transform_table(self, elem, doc):
        pass

    def transform_figure(self, elem, doc):
        pass


filters = {}

def register(name):
    def decorator(filter):
        filters[name] = filter
        return filter

default_filter = JournalFilter()
filters["default"] = [default_filter]
