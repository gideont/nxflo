# Intent-aware document generation

New jobs use pipeline version 2. Existing jobs without that version keep the original graph, system instructions, prompt identities, cached responses, recovery behavior and billing reconciliation. Prompt-policy versions are also pinned so a restart cannot silently change a paid request identity. A revision creates a new job and uses the new pipeline. Select the intended mode before generating a new document or revision.

## Three independent records

1. **Author intent:** the immutable original brief plus uploads explicitly marked Author material. The job stores the original brief, complete author material, its SHA-256 fingerprint, exact source spans for the thesis, audience, arguments, examples and messages, and the original heading sequence. Every source chunk is analyzed. Quotation matching tolerates capitalization, whitespace and an added terminal period, then stores the exact original source span; changed wording or financial numbers cannot become intent anchors. Numbered body headings define the narrative sequence ahead of subordinate figure or editorial headings.
2. **Empirical evidence:** reference uploads, fetched pages and transcripts. External extraction uses a neutral factual profile that retains contradictory findings and counterevidence, separate from author-intent extraction and writing/review profiles. Supporting summaries preserve provenance but do not replace the original author material. Empirical prose claims, table rows and charts need matching source evidence; unknown citations, unregistered numbers and mismatched data fail validation.
3. **Illustrative calculations:** typed, explicitly hypothetical input assumptions and deterministic financial outputs. The model proposes inputs; it does not author the output series, tables, formulas or chart numbers. Assumptions and model scope are printed with the results.

A proposal, intended feature or opinion may be communicated as the author's message without pretending that it is an independently observed result. An empirical claim remains subject to factual review even when it appears in author material. Nothing in the intent contract makes an external claim true.

## Modes

| Mode | Writing and review focus |
| --- | --- |
| Research report | Research question, evidence, methods, analysis and justified conclusions |
| Product concept white paper | Problem, opportunity, proposed solution, economic model, use cases, worked projections, risks and practical value |
| Technical paper | Architecture, mechanisms, interfaces, implementation constraints, worked examples and tradeoffs |
| Content-preserving rewrite | The original thesis, argument sequence, audience, examples and heading order; improve expression without substituting a different document |

The outline assigns every author anchor to a chapter and every required section to the manuscript. For a content-preserving rewrite with source headings, the original heading order and exact source positions determine these assignments, so incomplete model metadata cannot lose an example. These assignments remain drafting obligations, not proof of actual prose coverage. Small author briefs are included whole in all writing/review contexts. Longer material uses exact source-span retrieval for assigned anchors and the thesis, never summaries alone. Oversized contracts, chapters or publication contexts are rejected with a request to split the document; they are not silently truncated.

## Durable graph

The existing twelve workflow steps remain. Intent extraction runs within the summarization step and is checkpointed before reference summarization. Scenario planning runs with the outline. Invalid financial inputs receive one bounded, durably cached repair; failure of that repair stops generation without repeated billing on resume. The calculator derives the 90-day pilot from a longer forecast. A positive integer monetization month beyond the forecast correctly produces no monetized revenue within that horizon. The publication gate runs before HTML assembly. All model operations use the existing durable `Models` cache, provider isolation, cancellation, bounded request processes, unknown-outcome safeguards and billing records.

Drafting, rewriting and polishing receive the mode instructions, original author context, assigned anchors, supporting evidence and calculated scenario results. After each stage, validation binds coverage evidence to actual prose and checks provenance and publication defects. A bounded fidelity repair may repair a failed stage once. Reviewer suggestions are advisory and cannot override the author contract. Repeated failure blocks progress instead of silently publishing drift or generating an unlimited repair loop.

The final gate combines deterministic checks with an independent semantic review. It checks each author anchor and required section, authorial purpose, empirical accuracy, formula consistency and publication readiness. A model cannot pass merely by claiming that coverage is complete: its evidence must occur in the actual manuscript. Placeholder text, leaked editing instructions, repeated blanket disclaimers, unregistered equations, missing sections, unsupported numerical assertions and substantive drift block HTML publication.

The saved gate fingerprint binds the manuscript, author contract and financial models. HTML has its own fingerprint. HTML approval and PDF export reject changed or ungated content. Human HTML review remains required before PDF export.

## Financial calculation contract

Content-preserving rewrites first recognize explicit hypothetical USD monthly schedules using the original expense, base-case cash-flow and three-scenario revenue table columns. They retain exact source spans, check monthly arithmetic and totals, and calculate directly from those inputs instead of fitting a replacement growth curve. Startup expenses are counted once. Unsupported table layouts continue through input planning. Missing financing is reported as a calculated funding gap; it does not invalidate the business-case analysis. No participant allocation or distribution is invented.

Registered YouTube, SaaS and generic unit-based models support conservative, base and optimistic cases over 3–36 monthly periods. Worked investment examples include a 12-month forecast and a three-period, 90-day pilot. Inputs are bounded and finite; currencies and time periods are explicit. Cash amounts are rounded consistently to cents.

- Month zero contains initial project expenditure. Monthly receipts and operating cash payments occur at period end.
- YouTube views derive from video volume, views per video and growth. Revenue is zero before the stated monetization month. The simplified model also delays sponsorship and affiliate receipts to that month.
- SaaS closing customers equal retained opening customers plus new customers; subscription revenue and variable costs use that customer count.
- Project cash flow excludes financing contributions and distributions. Participant time is a separate non-cash opportunity cost. Economic gain is shown alongside cash gain.
- Project ROI divides net project gain by initial project expenditure. Participant returns use each participant's actual cash funding. Zero investment produces an undefined ROI, not infinity.
- Peak cumulative cash deficit determines the funding requirement. A forecast may never break even. Distributions are not allocated when the model has an unfunded cash deficit; base-case examples must disclose sufficient funding.
- Monthly discount rate is derived from the annual rate. NPV includes the initial outflow at time zero. IRR is reported only for a conventional sequence with one sign change and a bracketed root; other cases return undefined. Annualized IRR compounds the monthly rate.
- Participant capital recovery and agreed profit shares are separate. Rounding uses largest-remainder cent allocation so distributions balance exactly. Hours never silently become ownership.

The generated financial section includes an assumption register, scenario comparison, monthly projections, opportunity costs, funding and return metrics, participant distributions, formula definitions and seven kinds of calculated visualizations: revenue/expenses, cumulative cash flow, cost composition, three-scenario comparison, break-even, ROI sensitivity and participant funding/returns. Colors follow report branding. Tables stack on phones and provide readable assumptions and numerical results alongside the figures.

Period/sign conventions are consistent with the primary [NPV](https://numpy.org/numpy-financial/latest/_api_stubs/numpy_financial.npv.html) and [IRR](https://numpy.org/numpy-financial/latest/_api_stubs/numpy_financial.irr.html) definitions. The calculator is implemented locally and does not depend on a provider generating mathematics or execute model-written code.

## Verification and limits

`tests/fixtures/investment-return-simulator.md` preserves the original product brief with participant names de-identified. Regression provider fixtures are transparent, deterministic and incur no provider charges. Tests cover actual graph execution, HTML/PDF rendering, original intent retention, FP&A and partnership use cases, profitable/loss-making examples, known formula results, charts and tables, rejected drift and publication defects, source-role separation, cached-response reuse, shutdown and HTML approval integrity. Browser tests use an isolated authenticated app at 1440, 375, 320 and 430px.

These tests prove pipeline contracts and rejection behavior; they do not measure every live model's writing quality. The semantic publication review is an automated editorial assessment, not proof that an external source is true. The retained human preview supports the final publication decision. Cost planning includes original-author context, extraction, hypothetical-input planning, publication checks and a bounded repair allowance; it remains an estimate rather than a total spend cap.

## Generator controls and document versions

The configuration collapses while following a job and can be reopened without interrupting generation. The form uses the original brief for content and references; the separate research/upload controls are removed and new form submissions disable paid web discovery. Existing jobs retain their saved source data, requests and recovery records. Resume sits beside the interrupted step heading.

New documents use version 1.0. Author-submitted corrections and revisions add decimal 0.1 to the latest version in the document family, including 1.9 → 2.0. An expandable setting exposes an explicit manual override; duplicate revision labels are rejected. The immutable version history is rendered as the final document section, after contact details. Resuming the same job never increments its version.

Draft, polish and rewrite validation now collects typed chapter errors before repair, including malformed metadata and unknown formula IDs. The equation symbol `net_cash_flow` is canonicalized to the existing `cash_flow` registry ID; arbitrary formula names remain invalid. Affected chapters receive one repair at stable original chapter indices, so correct drafts and completed repairs remain cached across restarts. Repair evidence uses strictly bounded paragraph indices, bound by the server to actual returned prose; it cannot certify an absent quotation or a paraphrased summary. Every repaired manuscript still passes the full original-intent, provenance and publication gates.

Saved repair responses are loaded as unapproved working candidates and revalidated, rather than resubmitted when a local validator is corrected. Intent evidence can bind to a literal original statement already present in the prose; an unambiguous one-past-end index is corrected only when the actual final paragraph supports that author anchor. Content-preserving rewrites may retain an omitted, nonnumeric closing statement verbatim from an original heading; editorial directives and numerical claims are excluded from this fallback. No fabricated prose is added.

Calculator group IDs occupy a separate namespace from empirical sources. Financial chart requests using those IDs are accepted only when their numbers match a registered, recomputed figure recipe and their retained input spans match the original brief. The renderer uses the calculator's values and labels, marks the figures hypothetical, and places them in the corresponding chapters. Incorrect numeric series and unknown sources continue through empirical verification and are rejected.

Validated calculated-figure references are server-owned metadata. Rewriting and polishing retain them even when model schemas omit rendering fields, and each reference is revalidated against the calculator before publication.

Final publication review receives the rendered asset inventory and registered supplemental calculations, not prose alone. Source-owned visuals include financial figures, process diagrams, experiment timelines, product panels and the closing concept. Economic capacity benefit is distinguished from realized cash savings; returns on initial expenditure and total cash expenditure have explicit, separate denominators. Review evidence uses constrained publication-block IDs bound by the server to actual paragraphs, tables, figures and calculations. Independent negative judgments still reject publication. Approval fingerprints include the new artifact inventory and calculations while preserving legacy approval fingerprints for older jobs.

Publication checks also receive explicit peak-funding/startup multiples and cumulative cash recovery checkpoints computed from the verified schedule. Arithmetic from hypothetical inputs remains distinct from empirical evidence. For final-review responses only, a decoder may remove the impossible dangling `,"}` token outside string literals; it never changes values, infers missing fields, completes truncated JSON, or overrides a negative review. Saved raw provider responses remain unchanged for audit and billing.

The cover uses embedded vector artwork in the Nexusflow navy/wave style. Contents explicitly starts on the page after the cover. Authenticated HTML `?view=1` responses apply print CSS and locally hosted Paged.js 0.4.3 to display A4 sheets with page navigation and zoom. Browser pagination and PDF export use their respective rendering engines. The preview remains isolated in a scripts-only sandbox; the original downloadable HTML and its approval hash are unchanged by viewing.
