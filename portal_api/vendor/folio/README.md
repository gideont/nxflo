# Folio report design system

Source: https://github.com/abhirajsingh101/folio
Revision: f8ad00c269a8999cb39f37bb83bfe2118a523543 (0.7.0)
License: MIT, retained in LICENSE.

base.css, report.css and report-template.html are unmodified upstream assets.
The template is the structural reference for generation_document.py; the two
stylesheets are embedded into every generated HTML document by generation_layout.py.
Nexusflow's adapter adds brand tokens, responsive screen layout, contact details
and revision records. WeasyPrint renders that same self-contained HTML using
our existing embedded-image-only URL fetcher. No Folio CLI, chart scripts,
external fonts or unrestricted asset fetches execute in the worker.

To update: review a pinned upstream revision, replace these assets and LICENSE,
update this record, then run document browser and generation-engine tests.
