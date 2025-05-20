import json
import panflute as pf
from panflute import stringify, run_filter, Header, RawBlock, RawInline, convert_text, Block
from texmark.logs import logger
import io

def panflute2latex(elements, wrap='none') -> str:

    # logger.warning(f"Converting {len(elements)} elements to LaTeX")
    # for i, elem in enumerate(elements):
    #     logger.warning(f"Element: {i}: {type(elem)} {stringify(elem)}")

    doc = pf.Doc(*elements)

    # This breaks the figure environment
    return pf.convert_text(
        doc,
        input_format='panflute',
        output_format='latex',
        # extra_args=[f'--wrap={wrap}']
    )

    # # This also breaks the figure environment (no Fig ID, caption duplicated and added after the figure outside the figure environment)

    # # Convert doc → markdown
    # markdown = pf.convert_text(doc, input_format='panflute', output_format='markdown')

    # logger.warning(f"Markdown: {markdown}")

    # # Now render that markdown as LaTeX using Pandoc (with promotion logic)
    # latex = pf.convert_text(
    #     markdown,
    #     input_format='markdown',
    #     output_format='latex',
    #     extra_args=[f'--wrap={wrap}']
    # )

    # return latex


class SectionTracker:
    def __init__(self):
        self.active_section = None
        self.section_content = []
        self.section_level = 0
        self.sections = {}

    def reset(self):
        if self.active_section:
            self.sections[self.active_section] = {
                'content': self.section_content,
                'level': self.section_level
            }
        self.active_section = None
        self.section_content = []
        self.section_level = 0


# class SectionFilter:
#     def __init__(self, extract_sections, sections_map={}, remap_command_sections={}):
#         self.extract_sections = extract_sections
#         self.sections_map = sections_map or {}
#         self.remap_command_sections = remap_command_sections or {}

#     def prepare(self, doc):
#         self.tracker = SectionTracker()

#     def action(self, elem, doc):
#         tracker = self.tracker

#         # Skip if not a block element --> this is handled in finalize + `isinstance(elem, pf.Block)` in this action
#         # if isinstance(elem, pf.Doc):
#         #     tracker.reset()

#         # Header processing
#         if isinstance(elem, Header):
#             title = elem.identifier

#             # Check if we're exiting a section
#             if tracker.active_section and elem.level <= tracker.section_level:
#                 tracker.reset()

#             # Check if we're entering a target section
#             if title in self.extract_sections:
#                 tracker.reset()
#                 tracker.active_section = title
#                 tracker.section_level = elem.level
#                 return []  # Remove original header

#             # Check if the header is a target section for remap header command
#             if title in self.remap_command_sections:
#                 # Replace header with the remapped command
#                 command = self.remap_command_sections[title]
#                 return RawBlock(command, format='latex')


#         # Content collection
#         if tracker.active_section and isinstance(elem, pf.Block):
#             tracker.section_content.append(elem)
#             return []  # Remove from main flow


#     def finalize(self, doc):
#         tracker = self.tracker
#         tracker.reset()  # Capture last section

#         # Convert collected sections to LaTeX
#         for section in self.extract_sections:
#             meta_key = self.sections_map.get(section, section)
#             doc.metadata.setdefault(meta_key, [])
#             if section in tracker.sections:
#                 inline_elements = tracker.sections[section]['content']
#                 latex = panflute2latex(inline_elements)
#                 doc.metadata[meta_key].append(RawInline(latex, format='latex'))

class SectionFilter:
    def __init__(self, extract_sections, sections_map={}, remap_command_sections={}):
        self.extract_sections = extract_sections
        self.sections_map = sections_map or {}
        self.remap_command_sections = remap_command_sections or {}

    def prepare(self, doc):
        self.sections = {}
        self.extract_sections.extend(doc.get_metadata('extract_sections', []))
        self.sections_map.update(doc.get_metadata('sections_map', {}))
        self.remap_command_sections.update(doc.get_metadata('remap_command_sections', {}))
        self.collect_figures_and_tables = doc.get_metadata('collect_figures_and_tables', False)

    def action(self, elem, doc):
        # Only record section headers
        if isinstance(elem, pf.Header):
            doc.current_section = elem.identifier
        return None

    def finalize(self, doc):
        new_blocks = []
        current = None
        collecting = False
        section_level = None
        figure_blocks = []
        tables_blocks = []

        # Ensure section storage
        collected = {key: [] for key in self.extract_sections}
        collected_figures = {key: [] for key in self.extract_sections}
        collected_tables = {key: [] for key in self.extract_sections}

        logger.warning(f"Figure at end: {self.collect_figures_and_tables}")

        for blk in doc.content:
            if isinstance(blk, pf.Header):
                sid = blk.identifier
                if collecting:
                    collecting = False
                if sid in self.extract_sections:
                    current = sid
                    collecting = True
                    section_level = blk.level
                    # collected[sid].append(blk)
                    continue  # skip header from main doc

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

            # Get remapped metadata key if any
            meta_key = self.sections_map.get(sec_id, sec_id)

            # Render LaTeX (with figure promotion)
            latex_str = panflute2latex(blocks)
            latex_inline = pf.RawInline(latex_str, format='latex')

            # Store as MetaList of RawInline(s)
            if meta_key not in doc.metadata:
                doc.metadata[meta_key] = pf.MetaList(latex_inline)
            else:
                doc.metadata[meta_key].content.append(latex_inline)


def main(doc=None):
    extractor = SectionFilter(
        extract_sections=[],
    )
    return run_filter(extractor.action, prepare=extractor.prepare, finalize=extractor.finalize, doc=doc)

if __name__ == '__main__':
    main()