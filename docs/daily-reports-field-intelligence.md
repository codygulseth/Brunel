# Daily Reports and Field Intelligence

Brunel preserves each project day and daily-report revision as a project-scoped record with immutable source content, hashes, structured observations, and exact source locators. CSV, JSON, PDF, TXT, and Markdown inputs are supported locally; deterministic extraction produces proposals that require human review.

Field records cover reported weather, aggregate manpower, work, equipment, deliveries, inspections, tests, safety, quality, visitors, significant events, constraints, disruptions, and photo metadata. Brunel does not perform facial recognition, identify workers, infer production from images, store payroll details, approve work, or make regulatory conclusions. `received`, `accepted`, `stored`, and `installed` remain distinct concepts.

Reports move through draft, review, approval, and explicit internal issue. Issued revisions are immutable; corrections create a new revision. Drafting uses confirmed records by default. Weather and reported constraints do not establish contractual delay, causation, responsibility, concurrency, entitlement, or schedule impact.

Schedule-link and progress records are proposals. Human acceptance records a decision but never updates schedule activity status, dates, or percent complete automatically. Omitted work is not assumed unperformed, and `completed_reported` is not schedule confirmation. No schedule write-back or automatic workflow closure exists.

The development API and `daily-*`/`field-*` CLI commands expose creation, ingestion, analysis, review, draft/issue, dashboards, weekly summaries, search, and cited Q&A. Source files, generated exports, photos, audit data, and local notification requests remain under ignored storage. External models and notification delivery are disabled by default.
