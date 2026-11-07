# Nexusflow visual system

The site uses a shared enterprise engineering design system in `styles.css`.
Deep navy feature sections contrast with cool grey content areas, white cards,
and restrained blue links and actions. Instrument Sans is the only webfont, self-hosted as a variable WOFF2 with its OFL license in `fonts/`;
the existing logo retains its original colors, shape, and wordmark.
All pages continue to use the shared header and footer templates.

## Photography

The replacement photographs were generated with the built-in imagegen tool for
this redesign. They depict illustrative engineering and collaboration scenarios,
not actual Nexusflow employees or offices. No third-party stock assets are used.

- `images/engineering-collaboration.webp`: professionals reviewing analytics in
  a Vancouver workspace. Used on Home.
- `images/engineering-workbench.webp`: engineers reviewing measurements at an
  electronics R&D bench. Used on Services.
- `images/about-team-collaboration.webp`: Black and Asian engineering professionals
  reviewing system architecture plans. Used on About.
- `images/contact-client-consultation.webp`: Black and Asian professionals in a
  client consultation. Used on Contact.
- Each has an optimized 768px responsive variant.
- Prompts for the About and Contact photos are recorded in `photo-prompts.md`.
- Social preview images reference the same new photography. SEO titles,
  descriptions, canonical URLs, structured service data, and indexability remain
  unchanged.

The legacy illustrations remain in the source asset archive but are not used
by pages or social previews. The Vancouver footer asset keeps its established
path and now uses precise architectural linework instead of decorative art.

## Interaction and responsive behavior

The homepage presents four editorial capabilities with all nine original service
topics visible, alternating engineering photography and open text sections.
Individual service-page FAQ controls retain their native behavior.
Navigation remains visible at all widths and uses system typography so font loading cannot shift its alignment. Buttons, menu links, disclosures,
and mobile footer links have at least 44px touch targets. Focus indicators are
visible, and reduced-motion preferences disable transitions and smooth scrolling.
The stable scrollbar gutter keeps shared navigation aligned between pages.

Use `python3 build.py` and serve `dist/`, or use `bash 3_preview.sh`, to preview
expanded source templates. Existing browser checks cover native scrollbars,
mobile overflow, shared footers, service FAQs, and mouse, keyboard, and touch
interactions at widths down to 320px.

## Homepage capability content map

- Data Engineering & Architecture: database transfers and ETL, scheduled transfers
  and backups, pandas/legacy job limits, Spark/Databricks distributed workloads,
  data lakes, lakehouse architecture, ETL/ELT and storage scale.
- Systems & Industrial Integration: business applications, APIs, files and scripts,
  validation and manual handoffs; industrial/IoT collection using Modbus, OPC UA,
  MQTT, SNMP, Kafka and APIs for pipelines, monitoring and reporting.
- Analytics & Intelligence: dashboard trust, data quality, refresh pipelines and
  Power BI; continuously arriving data, AI workflows, trends, anomaly detection
  and near-real-time visibility for earlier action.
- Automation & Applications: CSV exports, spreadsheet cleanup, recurring collection
  and report refreshes; manual information copying, internal tools and workflow
  integrations.

All five original links to individual service pages remain in the showcase. The
existing `#examples` anchor remains valid. Two existing responsive engineering
photos accompany the first two capabilities; the hero photograph is unchanged.
`tests/check_home_capabilities.py` replaces the retired disclosure-card check.

## Small tasks and outsourcing

The homepage adds six always-visible practical examples beneath the four core
capabilities. Simple shared SVG icons and horizontal dividers replace card
containers. The existing hero, capabilities, navigation and footer are retained.
`what-can-we-help-you-with.html` preserves all nine original homepage questions,
explanations and five service links, arranged in five plain-English categories.
It is linked from both the homepage CTA and the Services page, uses Services as
its active navigation section, and is registered in the normal SEO/sitemap build.
`tests/fixtures/original-task-examples.json` preserves the source copy for content
verification; `tests/check_small_tasks.py` checks the full journey and layouts.
