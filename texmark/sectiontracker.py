import panflute as pf
from panflute import run_filter
from texmark.logs import logger


def panflute2latex(elements, wrap='none') -> str:
    doc = pf.Doc(*elements)
    return pf.convert_text(
        doc,
        input_format='panflute',
        output_format='latex',
        # Match the body render (build.py) so citations in extracted sections
        # (e.g. an appendix) become \citet/\citep rather than literal "@key".
        extra_args=['--natbib'],
    )


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


class SectionFilter:
    def __init__(self, extract_sections, sections_map=None, remap_command_sections=None, drop_sections=()):
        self.extract_sections = list(extract_sections)
        self.sections_map = dict(sections_map or {})
        self.remap_command_sections = dict(remap_command_sections or {})
        self.drop_sections = list(drop_sections)

    def prepare(self, doc):
        # Per-run effective config = declared config + the document's own
        # YAML additions, kept on separate attributes. The declared values
        # must never be mutated in place: filter instances are module-level
        # and shared across builds, so extending them here would leak one
        # document's YAML config into every later build of the same process
        # (repeated builds in --watch mode, companions, embeds).
        self._extract_sections = self.extract_sections + _as_list(
            doc.get_metadata('extract_sections', []))
        self._sections_map = {
            **self.sections_map,
            **(doc.get_metadata('sections_map', {}) or {}),
        }
        self._remap_command_sections = {
            **self.remap_command_sections,
            **(doc.get_metadata('remap_command_sections', {}) or {}),
        }
        self.collect_figures_and_tables = doc.get_metadata('collect_figures_and_tables', False)

    def action(self, elem, doc):
        return None

    def finalize(self, doc):
        logger.debug(f"Finalizing sections: {self._extract_sections}")
        new_blocks = []
        current = None
        collecting = False
        section_level = None
        figure_blocks = []
        tables_blocks = []

        all_collect = list(self._extract_sections) + list(self.drop_sections)

        # Ensure section storage
        collected = {key: [] for key in all_collect}
        collected_titles = {}
        collected_figures = {key: [] for key in all_collect}
        collected_tables = {key: [] for key in all_collect}

        for blk in doc.content:
            if isinstance(blk, pf.Header):
                sid = blk.identifier
                # Only a same-or-higher-level header ends the current section; a
                # deeper subsection is part of it and falls through to be collected.
                if collecting and blk.level <= section_level:
                    collecting = False
                if sid in all_collect:
                    current = sid
                    collecting = True
                    section_level = blk.level
                    collected_titles[sid] = pf.stringify(blk)
                    logger.debug(f"Collecting section: {sid} level: {blk.level}")
                    continue  # skip header from main doc
                if not collecting and sid in self._remap_command_sections:
                    # Headers the template's document class provides a command
                    # for (e.g. copernicus \introduction) are replaced by that
                    # command; the section's content stays in the body.
                    new_blocks.append(pf.RawBlock(
                        self._remap_command_sections[sid], format='latex'))
                    continue

            if collecting:
                if self.collect_figures_and_tables and isinstance(blk, pf.Figure):
                    # Store figure blocks separately
                    collected_figures[current].append(blk)
                elif self.collect_figures_and_tables and isinstance(blk, pf.Table):
                    # Store figure blocks separately
                    collected_tables[current].append(blk)
                else:
                    collected[current].append(blk)
            else:
                if self.collect_figures_and_tables and isinstance(blk, pf.Figure):
                    figure_blocks.append(blk)
                elif self.collect_figures_and_tables and isinstance(blk, pf.Table):
                    tables_blocks.append(blk)
                else:
                    new_blocks.append(blk)

        # add figures to the end of the document, preceded by '\clearpage'
        for blk in tables_blocks + figure_blocks:
            # Add a \clearpage before each figure
            new_blocks.append(pf.RawBlock('\\clearpage', format='latex'))
            new_blocks.append(blk)

        doc.content = new_blocks

        # Add collected_figures to collected, preceded by '\clearpage'
        for sec_id, blocks in collected_tables.items():
            for blk in blocks:
                # Add a \clearpage before each figure
                collected[sec_id].append(pf.RawBlock('\\clearpage', format='latex'))
                collected[sec_id].append(blk)

        for sec_id, blocks in collected_figures.items():
            for blk in blocks:
                # Add a \clearpage before each figure
                collected[sec_id].append(pf.RawBlock('\\clearpage', format='latex'))
                collected[sec_id].append(blk)

        # Inject extracted sections into metadata
        for sec_id, blocks in collected.items():
            if not blocks:
                continue

            if sec_id in self.drop_sections:
                logger.warning(
                    f"dropping section '{collected_titles.get(sec_id, sec_id)}' "
                    f"(not used by this template)"
                )
                continue

            # Get remapped metadata key if any
            meta_key = self._sections_map.get(sec_id, sec_id)

            # Render LaTeX (with figure promotion)
            latex_str = panflute2latex(blocks)
            latex_inline = pf.RawInline(latex_str, format='latex')

            # Store as MetaList of RawInline(s)
            if meta_key not in doc.metadata:
                doc.metadata[meta_key] = pf.MetaList(latex_inline)
            else:
                doc.metadata[meta_key].content.append(latex_inline)

            # Store the original heading text in <meta_key>titles, in parallel
            # with <meta_key>. Templates that want the original heading (e.g.
            # ametsoc's \appendixtitle) can read appendixtitles[i]; others
            # simply ignore it.
            titles_key = f"{meta_key}titles"
            title_inline = pf.MetaString(collected_titles.get(sec_id, ''))
            if titles_key not in doc.metadata:
                doc.metadata[titles_key] = pf.MetaList(title_inline)
            else:
                doc.metadata[titles_key].content.append(title_inline)


def main(doc=None):
    extractor = SectionFilter(
        extract_sections=[],
    )
    return run_filter(extractor.action, prepare=extractor.prepare, finalize=extractor.finalize, doc=doc)


if __name__ == '__main__':
    main()
