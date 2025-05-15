# texmark

Write scientific articles in markdown


## Installation

for development, after cloning:

    pip install -e .

and soon:

    pip install texmark

## Example

See [example.md](example.md) for a sample markdown file with frontmatter metadata

The command to convert the markdow to tex is:

    texmark example.md

And to convert to PDF

    texmark example.md --pdf

See the example tex and pdf results in [build](/build)