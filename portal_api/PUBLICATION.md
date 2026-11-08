# Publication and verification

Generation retains the immutable author brief and intent contract. Missing independent factual evidence does not authorize a change to the author's argument.

`generation_verification.py` classifies the independent review separately from document integrity:

- **PASS**: structural, intent, source and calculation checks pass.
- **WARNING**: a complete draft contains factual assertions requiring verification. Accuracy is not certified (`passed: false`). The renderer adds claim markers, a cover label, running-header labels and the exact outstanding issues. HTML and PDF are delivered as `needs_review`, without waiting for final-HTML approval.
- **BLOCKED**: fabricated citations/quotations, contradictory calculations, missing required content, substantive drift or unusable output. The interface disables unchanged recovery. Corrected content, evidence or criteria must change the fingerprint before a fresh review can run.

Pure authorial proposals are not empirical claims. Author-sourced empirical statements and regulatory assertions require independent evidence; citing the original brief is not independent verification. Source quotations remain checked exactly. Untraceable model-generated numbers, invalid empirical graphics and fabricated citations are not downgraded to warnings. The calculator is re-run before publication, including when resuming from saved assembly state.

Optional regulatory research reuses the existing single reserved web search and spending cap. Only authoritative government/regulator pages are downloaded; search summaries alone do not establish verification. Unsupported statements retain qualifications when research is disabled, unavailable, exhausted or inconclusive. Databricks web-discovery limitations and uncertain-provider-outcome safeguards remain in force.

Publication review identities bind manuscript, rendered assets, source packet, required criteria and validation policy version. Raw reviews are checkpointed before decision handling. A legacy rejected assembly checkpoint can adopt its exact completed reviewer responses once, decoding them through the original response decoder. Subsequent changes invalidate that binding. No writing chapters or completed provider responses are discarded.

The bounded correction for missing evidence is deterministic reader-facing qualification; it does not request another AI rewrite or re-review of unchanged work. Existing chapter repairs remain bounded. Serious unresolved defects remain blocked rather than cycling through paid retries. Historical approved artifacts retain their original fingerprint and HTML hash; rendering a new artifact requires the new gate.

`tests/test_verification_delivery.py` covers the Vancouver/California regulatory rejection, both downloadable formats, repeated recovery without new provider requests, evidence-sensitive cache invalidation, optional primary-source retrieval, proposals versus facts, and critical failures. `tests/check_verification_delivery.py` checks the warning interface and paginated preview at 1440/375/320/430 pixels.
