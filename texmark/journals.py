"""Journal filter registry: which filter chain runs for which template.

Populates ``texmark.shared.filters`` (template name -> filter chain) and
provides ``run_filters``, the entry used both in-process by build.py and by
the ``texmark-journal`` pandoc subprocess filter. Per-journal behavioural
hooks (citation command rewriters, front-matter extraction) live here too.
"""

import importlib

import panflute as pf

from texmark.logs import logger
from texmark.shared import filters, Filter, BOOK_FAMILY_TEMPLATES
from texmark.sectiontracker import SectionFilter, panflute2latex
from texmark.filters.tabular import table_to_latex
from texmark.filters.embed import embed_filter
from texmark.filters.crossref import crossref_filter
from texmark.filters.equations import equations_filter
from texmark.filters.images import strip_leading_slash, resolve_image_paths
from texmark.filters.figures import (
    tag_figures,
    extract_table_identifier,
    stringify_captions,
    apply_figure_defaults,
)


basic_filters = [
    embed_filter,
    crossref_filter,
    equations_filter,
    strip_leading_slash,
    resolve_image_paths,
    extract_table_identifier,
    stringify_captions,
    tag_figures,
    apply_figure_defaults,
    table_to_latex,
]

default_filters = basic_filters

# Beamer presentations: a slim chain. apply_figure_defaults is dropped because
# its figure*/`figure-span: full` behaviour is article-class-specific (beamer
# frames have no two-column figure* environment), and no SectionFilter is
# registered because slide decks have no abstract / data-availability /
# appendix sections to extract into the preamble.
beamer_filters = [f for f in basic_filters if f is not apply_figure_defaults]

for _beamer_name in ["beamer", "slides", "presentation"]:
    filters[_beamer_name] = beamer_filters

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
        drop_sections=['author-contributions'],
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


def apacite_cite(elem, doc):
    """Rewrite natbib-style citations to apacite (used by agujournal2019).

    Markdown ``@key`` becomes panflute Cite(mode=AuthorInText) which pandoc's
    natbib emitter would render as ``\\citet{key}``. apacite uses ``\\citeA``
    for the same in-text form. Bracketed ``[@key]`` (NormalCitation) maps to
    apacite's plain ``\\cite``.
    """
    if isinstance(elem, pf.Cite):
        keys = ",".join(c.id for c in elem.citations)
        first_mode = elem.citations[0].mode if elem.citations else 'NormalCitation'
        cmd = r'\citeA' if first_mode == 'AuthorInText' else r'\cite'
        return pf.RawInline(f'{cmd}{{{keys}}}', format='latex')


agu_filters = [
    *basic_filters,
    apacite_cite,
    SectionFilter(
        extract_sections=[
            'abstract', 'plain-language-summary', 'keypoints', 'key-points',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'plain-language-summary': 'plainlanguagesummary',
            'key-points': 'keypoints',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            **{section: 'appendix' for section in si_sections},
        },
        drop_sections=['author-contributions'],
    ),
]

for journal in ["agujournal", "agu", "jgr", "grl", "james", "earthsfuture", "wrr", "rog"]:
    filters[journal] = agu_filters


springernature_filters = [
    *basic_filters,
    force_cite,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'funding', 'ethics', 'ethics-approval',
            'author-contributions', 'competing-interests',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            'ethics-approval': 'ethics',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

for journal in ["springernature", "springer", "nature", "naturecomms", "natclimchange", "natgeoscience", "scirep"]:
    filters[journal] = springernature_filters


pnas_filters = [
    *basic_filters,
    force_cite,
    SectionFilter(
        extract_sections=[
            'abstract', 'keywords',
            'significance', 'significance-statement',
            'acknowledgements', 'acknowledgments',
            'data-availability', 'data-availability-statement',
            'author-contributions',
            'competing-interests', 'declaration', 'author-declaration',
            'equal-authors',
        ] + si_sections,
        sections_map={
            'acknowledgments': 'acknowledgements',
            'significance-statement': 'significance',
            'data-availability': 'dataavailability',
            'data-availability-statement': 'dataavailability',
            'author-contributions': 'authorcontribution',
            'competing-interests': 'competinginterests',
            'declaration': 'competinginterests',
            'author-declaration': 'competinginterests',
            'equal-authors': 'equalauthors',
            **{section: 'appendix' for section in si_sections},
        },
    ),
]

filters['pnas'] = pnas_filters


class FrontmatterFilter:
    """Lift # Dedication / # Preface / # Foreword sections into metadata.

    Only active for book-family templates. YAML wins: when a front-matter key
    is declared in YAML *and* a matching ``# Section`` header also appears in
    the body, the YAML value is kept and the body section is discarded (with a
    warning log).  ``list_of_figures`` and ``list_of_tables`` are pure YAML
    flags — the filter does not need to lift them; the templates read them
    directly.
    """

    FRONT_SECTIONS = ['dedication', 'preface', 'foreword']

    def __init__(self):
        self._skip = False
        self._yaml_has = {}

    def prepare(self, doc):
        template = doc.get_metadata('journal', {}).get('template', '')
        self._skip = template not in BOOK_FAMILY_TEMPLATES
        self._yaml_has = {}
        if self._skip:
            return
        for key in self.FRONT_SECTIONS:
            self._yaml_has[key] = doc.get_metadata(key, None) is not None

    def action(self, elem, doc):
        return None

    def finalize(self, doc):
        if self._skip:
            return

        new_blocks = []
        current_key = None
        current_content = []

        for blk in doc.content:
            if isinstance(blk, pf.Header):
                if current_key is not None:
                    self._flush(current_key, current_content, doc)
                    current_key = None
                    current_content = []
                sid = blk.identifier.lower()
                if sid in self.FRONT_SECTIONS:
                    current_key = sid
                    continue
                new_blocks.append(blk)
                continue
            if current_key is not None:
                current_content.append(blk)
            else:
                new_blocks.append(blk)

        if current_key is not None:
            self._flush(current_key, current_content, doc)

        doc.content = new_blocks

    def _flush(self, key, content, doc):
        if self._yaml_has.get(key):
            logger.warning(
                f"texmark: '{key}' declared in both YAML and as a "
                f"'# {key.capitalize()}' markdown section; "
                f"YAML value takes precedence."
            )
            return
        if content:
            latex_str = panflute2latex(content)
            doc.metadata[key] = pf.MetaString(latex_str)


frontmatter_filter = FrontmatterFilter()

# Book-family templates: basic filters + front-matter section extraction.
book_filters = list(basic_filters) + [frontmatter_filter]

filters['book'] = book_filters
filters['report'] = book_filters


def _surface_chapter_style(doc):
    """Copy the hyphenated ``chapter-style`` YAML key to ``chapter_style``.

    The memoir template emits ``\\chapterstyle{ {{ chapter_style }} }``, but
    Jinja cannot reference a context key containing a hyphen (it parses as a
    subtraction). We surface the value under a Jinja-safe name so the template
    can read it; when the key is absent the template falls back to its default.
    """
    cs = doc.get_metadata('chapter-style', None)
    if cs:
        doc.metadata['chapter_style'] = pf.MetaString(str(cs))


memoir_filters = list(basic_filters) + [Filter(prepare=_surface_chapter_style), frontmatter_filter]

filters['memoir'] = memoir_filters


def _surface_classicthesis_options(doc):
    """Copy the hyphenated ``classicthesis-options`` YAML key to
    ``classicthesis_options``.

    The classicthesis template emits
    ``\\usepackage[ {{ classicthesis_options }} ]{classicthesis}``, but Jinja
    cannot reference a context key containing a hyphen (it parses as a
    subtraction). We surface the value under a Jinja-safe name; when the key
    is absent the template loads the package with its own defaults.
    """
    opts = doc.get_metadata('classicthesis-options', None)
    if opts:
        doc.metadata['classicthesis_options'] = pf.MetaString(str(opts))


classicthesis_filters = list(basic_filters) + [
    Filter(prepare=_surface_classicthesis_options), frontmatter_filter
]

filters['classicthesis'] = classicthesis_filters


def run_filters(doc):

    if doc is not None:
        journal = doc.get_metadata('journal') or {}
    else:
        logger.warning('doc is None')
        journal = {'template': 'default'}

    if doc.get_metadata('filters_module'):
        filters_module = doc.get_metadata('filters_module')
        logger.info(f"Loading filters module: {filters_module}")
        importlib.import_module(filters_module)

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
