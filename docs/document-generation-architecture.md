# Intent-aware document generation

New jobs use pipeline version 2. Existing jobs without that version keep the original graph, system instructions, prompt identities, cached responses, recovery behavior and billing reconciliation. Prompt-policy versions are also pinned so a restart cannot silently change a paid request identity. A revision creates a new job and uses the new pipeline. Select the intended mode before generating a new document or revision.

## Three independent records

1. **Author intent:** the immutable original brief plus uploads explicitly marked Author material. The job stores the original brief, complete author material, its SHA-256 fingerprint, exact source spans for the thesis, audience, arguments, examples and messages, and the original heading sequence. Every source chunk is analyzed. A quote that does not match the original cannot become an intent anchor.
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

The outline assigns every author anchor to a chapter and every required section to the manuscript. Small author briefs are included whole in all writing/review contexts. Longer material uses exact source-span retrieval for assigned anchors and the thesis, never summaries alone. Oversized contracts, chapters or publication contexts are rejected with a request to split the document; they are not silently truncated.

## Durable graph

The existing twelve workflow steps remain. Intent extraction runs within the summarization step and is checkpointed before reference summarization. Scenario planning runs with the outline. The publication gate runs before HTML assembly. All model operations use the existing durable `Models` cache, provider isolation, cancellation, bounded request processes, unknown-outcome safeguards and billing records.

Drafting, rewriting and polishing receive the mode instructions, original author context, assigned anchors, supporting evidence and calculated scenario results. After each stage, validation binds coverage evidence to actual prose and checks provenance and publication defects. A bounded fidelity repair may repair a failed stage once. Reviewer suggestions are advisory and cannot override the author contract. Repeated failure blocks progress instead of silently publishing drift or generating an unlimited repair loop.

The final gate combines deterministic checks with an independent semantic review. It checks each author anchor and required section, authorial purpose, empirical accuracy, formula consistency and publication readiness. A model cannot pass merely by claiming that coverage is complete: its evidence must occur in the actual manuscript. Placeholder text, leaked editing instructions, repeated blanket disclaimers, unregistered equations, missing sections, unsupported numerical assertions and substantive drift block HTML publication.

The saved gate fingerprint binds the manuscript, author contract and financial models. HTML has its own fingerprint. HTML approval and PDF export reject changed or ungated content. Human HTML review remains required before PDF export.

## Financial calculation contract

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
