from texmark.sectiontracker import SectionProcessor
from texmark.shared import JournalFilter, register, filters, logger

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