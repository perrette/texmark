import json
import panflute as pf
from panflute import stringify, run_filter, Header, RawBlock, RawInline, convert_text, Block
from texmark.logs import logger
import io

def panflute2latex(elements, wrap='none') -> str:
    blocks = []
    inline_buffer = []

    for el in elements:
        if isinstance(el, pf.Block):
            # Flush any accumulated inlines before adding a block
            if inline_buffer:
                blocks.append(pf.Para(*inline_buffer))
                inline_buffer = []
            blocks.append(el)

        elif isinstance(el, pf.Inline):
            inline_buffer.append(el)

        else:
            raise TypeError(f"Unsupported element type: {type(el)}")

    # Flush remaining inlines into a final paragraph
    if inline_buffer:
        blocks.append(pf.Para(*inline_buffer))

    doc = pf.Doc(*blocks)

    # Safer output buffering
    buffer = io.BytesIO()
    writer = io.TextIOWrapper(buffer, encoding='utf-8')
    pf.dump(doc, writer)
    writer.flush()

    json_ast_str = buffer.getvalue().decode('utf-8')

    latex = pf.convert_text(
        json_ast_str,
        input_format='json',
        output_format='latex',
        extra_args=[f'--wrap={wrap}']
    )

    return latex



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


class SectionProcessor:
    def __init__(self, extract_sections, sections_map={}, remap_command_sections={}):
        self.extract_sections = extract_sections
        self.sections_map = sections_map or {}
        self.remap_command_sections = remap_command_sections or {}

    def prepare(self, doc):
        doc.tracker = SectionTracker()
        doc.extract_sections = self.extract_sections
        doc.sections_map = self.sections_map

    def action(self, elem, doc):
        tracker = doc.tracker
        # logger.warning(f"check elem {elem} {stringify(elem)}")

        # Header processing
        if isinstance(elem, Header):
            title = elem.identifier

            # Check if we're entering a target section
            if title in doc.extract_sections:
                tracker.reset()
                tracker.active_section = title
                tracker.section_level = elem.level
                # logger.warning(f"!!Remove {elem}")
                return []  # Remove original header

            # Check if we're exiting a section
            if tracker.active_section and elem.level <= tracker.section_level:
                # logger.warning(f"Exit {tracker.active_section} with {elem} {stringify(elem)}")
                # logger.warning(f"Last element of {tracker.active_section} {tracker.section_content[-1]}")
                # logger.warning(f"Remove last: {tracker.section_content[-1]} {stringify(tracker.section_content[-1])}")
                tracker.section_content = tracker.section_content[:-1]
                tracker.reset()

            # Check if the header is a target section for remap header command
            if title in self.remap_command_sections:
                # Replace header with the remapped command
                command = self.remap_command_sections[title]
                return RawBlock(command, format='latex')


        # Content collection
        if tracker.active_section:
            tracker.section_content.append(elem)
            return []  # Remove from main flow


    def finalize(self, doc):
        tracker = doc.tracker
        tracker.reset()  # Capture last section

        # Convert collected sections to LaTeX
        for section in doc.extract_sections:
            meta_key = doc.sections_map.get(section, section)
            if section in tracker.sections:
                inline_elements = tracker.sections[section]['content']
                latex = panflute2latex(inline_elements)
                doc.metadata[meta_key] = RawInline(latex, format='latex')


def main(doc=None):
    extractor = SectionProcessor(
        extract_sections=["introduction", "methods", "conclusions", "acknowledgements"],
    )
    return run_filter(extractor.action, prepare=extractor.prepare, finalize=extractor.finalize, doc=doc)

if __name__ == '__main__':
    main()