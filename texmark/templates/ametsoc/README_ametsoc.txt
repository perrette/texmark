1 September 2021, Version 6.0
==================================
Files in the 
American Meteorological Society
LaTeX Package
==================================
Copyright 2021, American Meteorological Society

This work may be distributed and/or modified under the
conditions of the LaTeX Project Public License, either version 1.3
of this license or (at your option) any later version.
The latest version of this license is in
http://www.latex-project.org/lppl.txt
and version 1.3 or later is part of all distributions of LaTeX
version 2005/12/01 or later.

This work has the LPPL maintenance status `maintained'.
The Current Maintainer of this work is the American Meteorological Society.
This work consists of the files ametsocV6.cls, ametsocV6.bst, amsdocsV6.pdf, and AMS_RefsV6.pdf.
==================================
You will be provided with a tarred, zipped LaTeX package containing 
17 files.

==================================
Basic Style File: ametsocV6.cls. 

The file ametsocV6.cls is the manuscript style file.  

Use \documentclass{ametsocV6} for your .tex document to
generate a PDF that follows all AMS guidelines for submission and peer review.  

Use \documentclass[twocol]{ametsocV6} for your .tex document
to generate a PDF that closely
follows the layout of an AMS journal page, including single spacing and two
columns.  This journal style PDF is only for the author's personal use, and
any papers submitted in this style will not be accepted.  

Always use \documentclass{ametsocV6} 
when generating a PDF for submission to the AMS. 

==================================
Template:

templateV6.tex is a file for the author to use to create their paper.

The file provides a basic blank template with some
section headings for authors to more easily enter their manuscript.

==================================
Bibliography Files:

ametsocV6.bst, references.bib, and AMS_RefsV6.pdf  

ametsocV6.bst is the bibliography style file. 

references.bib should be altered with your own bibliography information. 

AMS_RefsV6.pdf explains AMS reference style and contains detailed examples. 
Reference list included within is obtained from database2020.bib.

==================================
Documentation: 

Found in amsdocsV6.pdf, amspaperV6.tex/amspaperV6.pdf, and in this file, readme.txt.

==================================
Samples:
amssamp1V6.tex
amssamp1V6.pdf
amssamp2V6.tex
amssamp2V6.pdf
database2020.bib
FigOne.pdf
FigTwo.pdf
figure01.pdf
==================================
Help for Authors
==================================

For questions or problems related to submitting your LaTeX manuscript 
to the AMS, see the AMS LaTeX Submission Info webpage:

www.ametsoc.org/pubslatex

or contact latex@ametsoc.org

============================
Version History: 

 Version history

 7 May 2014 -- Nicole Rietmann, AMS
 Updated to version 4.1
 Changed draft line spacing from 1.66 to 2
 Added \bibpunct command to template

 12 May 2014 -- Nicole Rietmann, AMS
 Updated to version 4.2
 Added version and date to footer
 Changed line spacing from 2 to 2.25
 Added if/else statements for fig/table line spacing (\baselinestretch)
 Decreased vertical space after section heads
 Removed en dashes around page numbers
 Removed line after abstract
 Decreased vertical space after appendix title

 16 May 2014 -- Nicole Rietmann, AMS
 Updated to version 4.3
 Added command to fix equation line spacing

 19 May 2014 -- Nicole Rietmann, AMS 
 Updated to version 4.3.1
 Removed unnecessary \usepackage{tikz} command

 25 August 2014 -- Nicole Rietmann, AMS
 Updated to version 4.3.2
 Correction of \BAMS to \bams for journal command
 Addition of JAS to journal list in .cls and template
 Clarified appendix fig/table placement in template and amsdocs.pdf
 Addition of BAMS capsule instructions in template and amsdocs.pdf

 2 January to 31 July 2020 -- Nicole Rietmann, AMS
 Updated to version 5.0
 Addition of commands \usepackage{newtxtext} and \usepackage{newtxmath} to fix bug with some Greek letters not showing up properly in Times font
 Moved math commands to templateV5.tex file for greater visibility and easier manipulation, and added optional hmmax and bmmax commands to prevent "too many math alphabets" error.
 Addition of \usepackage{epstopdf} to resolve issues with certain programs not automatically converting eps files to pdf
 Made abstract margins wider
 Removed separate email command, email now included in corresponding author info
 Removed option to select journal name for two-column
 Added statement for preprint use of two-column version
 Updated references.bib, database2020.bib, and documentation to fix errors and include updates to AMS reference style and formatting
 Added instructions and commands to template and documentation for significance statement and data availability statement
 Removed paragraph indentation at beginning of abstract

 1 August 2021 -- Nicole Rietmann, AMS
 Updated to version 6.0
 Removed endfloat from ametsocV6.cls file; figures and tables will now be embedded in the paper instead of appearing at the end. This also resolves several other issues caused by endfloat conflicting with commands.
 Moved math commands from template file back to ametsocV6.cls.
 Added \usepackage{appendix}, \usepackage{mdframed}, \usepackage{cuted}, and \usepackage{setspace} for changes to appendix commands, significance statement/capsule box, and figure and table captions.
 Removed "appendcaption" commands; standard LaTeX appendix commands and standard figure, table, and equation commands and labels can be used.
 Changed draft line spacing to 1.75 (equivalent to Word 1.5 spacing)
 Changed affiliation style to use footnote letters, removed \extraauthor and \extraaffil commands
 Abstract header is now run into the first line of the abstract
 Significance statement/capsule is now set in its own box with new commands
 The \thanks command no longer applies symbols to footnotes or at author names
 In the .bst file, the text "doi:" now appears as "https://doi.org/".
 Instructions and example tables changed to place table captions below instead of above tables to be consistent with new submission guidelines.

 1 September 2021 -- Nicole Rietmann, AMS
 Updated to version 6.1
 Added \clearpage command before Acknowledgments to ensure that all figures from main paper appear before the References
 Changed significance statement and capsule commands to include line numbers and remove separate environment.
 Removed \usepackage{mdframed} and \usepackage{cuted} from class file, as they are no longer needed for significance statement/capsule 
