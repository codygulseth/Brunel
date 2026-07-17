# Submittal Automation

Brunel's canonical `submittal` module manages evidence-backed submittal requirements, register items, packages, reviews, official responses, resubmittals, and procurement dependencies. It is an internal workflow system—not an architect/engineer review authority, procurement platform, or external document-control integration.

## Evidence and requirement admission

`SubmittalRequirementExtractionService` scans project-scoped ingested specifications using deterministic rules. Each candidate retains its exact paragraph excerpt plus document, page, chunk, and specification-section citation. Repeated extraction reuses stable candidate identities. Optional provider assistance is disabled by default; failure or unsupported provider output retains deterministic candidates.

Candidates require an explicit accept, reject, not-applicable, or defer decision. Acceptance creates a canonical register item only after duplicate review. Merge and split operations are explicit and audited. Manual register creation remains available for requirements that cannot be extracted reliably.

## Register and package lifecycle

Register numbers are project-scoped, stable, and configurable as sequential or specification-prefixed numbers. The register tracks responsibility, dates, criticality, links, and procurement/schedule relationships. Package revisions preserve their attachments, content hash, evidence, deviations, corrections, creator, and issue state.

The workflow separates three authorities:

1. Brunel completeness review checks whether cited required document types and attachment metadata are present. It never claims technical compliance.
2. Internal review is a project-team decision. Any package revision invalidates prior internal approval and requires reapproval before issue.
3. Official disposition is recorded only when explicitly identified as an official design-team response. Informal comments remain separate, and Brunel response analysis is labeled inference.

Supported dispositions include approved, approved as noted, revise and resubmit, rejected, reviewed, no exception taken, make corrections noted, informational only, not reviewed, and void. Revise-and-resubmit creates a new immutable package revision with a correction checklist. Old revisions and responses remain available.

## Procurement, schedule, and staleness

Deterministic calendar-day calculations derive latest approval, release, and submit dates from the required-on-site date plus fabrication, shipping, processing, review, resubmittal, and buffer allowances. These dates are planning indicators. Brunel does not release procurement automatically: approved-as-noted corrections require explicit human confirmation.

Schedule relationships are references only; Brunel does not modify a schedule. RFI and project-change links are project-scoped and bidirectional where the neighboring service supports them. Revision/RFI changes may mark a package potentially stale, stale, or review-required. Closure and current-approved-package reporting fail closed until a human records a current assessment.

## Persistence, API, CLI, and Q&A

JSON repositories use schema versions, project scoping, optimistic concurrency, atomic replacement, corrupt-record isolation during list operations, and append-only audit events. Generated data belongs under `BRUNEL_DATA_DIRECTORY/submittals`; exports belong under the ignored `reports/submittals` root.

The development API exposes extraction and candidate review, register CRUD-style operations, assignments and procurement dates, packages and completeness, internal review and issue, responses and analysis, resubmittals, staleness, procurement release, logs, dashboards, audit, exports, and operational questions. HTTP responses omit local source paths while retaining citation identity.

Representative CLI flow:

```powershell
python -m app.cli submittal-extract --project-id demo-project --specification-section "26 24 13"
python -m app.cli submittal-candidates --project-id demo-project
python -m app.cli submittal-review-candidate --project-id demo-project --candidate-id subreq-id --decision accept --explanation "Verified against cited paragraph"
python -m app.cli submittal-package-create --project-id demo-project --submittal-id sub-id --submitter "Electrical Subcontractor" --included-type product_data --attachment product-data.pdf
python -m app.cli submittal-completeness --project-id demo-project --package-id package-id
python -m app.cli submittal-dashboard --project-id demo-project
```

Run the deterministic local scenario with:

```powershell
python -m app.cli submittal-demo --project-id synthetic-submittal-demo
```

## Legacy placeholder decision

The canonical `submittal.SubmittalRegisterItem` and `SubmittalPackage` models replace generic submittal placeholders for all lifecycle data. Existing `change_workflow.RelatedItem` records with `WorkflowType.SUBMITTAL` are retained only as optional compatibility pointers through `legacy_related_item_id`; the canonical module never treats them as authoritative.

## Current limitations

- No authentication, authorization, distributed database locking, or production tenant isolation.
- No Procore, Autodesk Construction Cloud, email, or external notification delivery.
- No automatic procurement action or schedule mutation.
- Text-bearing PDF, TXT, and Markdown attachments have deterministic content intelligence; Office files and images remain metadata-only, and there is no OCR, PDF form generation, drawing vision, or technical compliance determination.
- Deterministic extraction targets explicit text requirements; implicit, tabular, image-only, and cross-referenced requirements need human review.
- Optional model assistance has an interface but no provider is enabled by default.

Detailed attachment lineage, evidence mapping, comparison, search, and review behavior is documented in [Submittal Attachment Intelligence](submittal-attachment-intelligence.md).
