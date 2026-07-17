# Revision Review and Project Change Workflow

Revision findings describe document differences. Project changes describe how the project team reviews and resolves material findings. The workflow preserves that distinction and always links operational records back to immutable comparison and source-document citations.

```text
New revision ingested -> predecessor identified -> deterministic comparison
-> materiality policy -> project change register -> reviewer assignment
-> controlled review transition -> disposition -> linked/draft workflow action
-> resolution -> append-only audit -> stale detection -> regeneration/reconciliation
```

## Admission and register

`ChangeAdmissionService` applies versioned deterministic rules. Formatting-only findings are excluded by default. Human-review requirements, high severity, numeric/quantity/responsibility/approval changes, and configured construction categories admit a finding. Decisions retain rule reasons and policy version. `ProjectChangeService.generate_register` creates stable IDs and reuses existing records when the same comparison is processed again.

## Review controls

Assignments retain history by deactivating prior primaries rather than deleting them. State changes follow an explicit transition map. Under-review requires an assignment; rejection, cancellation, supersession, and information requests require reasons; resolution requires a summary; closure requires a disposition; stale records require acknowledgement before closure. Notes and audit events are append-only.

Dispositions are independent of status. Cost, schedule, and scope certainty remain `unknown`, `possible`, or `likely` unless a reviewer explicitly records `confirmed`. Brunel never promotes inferred impact to confirmed impact.

## Links and related drafts

Generic links cover RFIs, submittals, procurement items, schedule activities, owner decisions, change events/orders, quality, safety, commissioning, field issues, and external references. URLs accept only HTTP(S). Minimal internal related records are drafts, preserve source evidence, create an automatic workflow link, and are idempotent. They do not create external RFIs, submittals, or messages.

The `rfi` package now replaces the generic RFI draft as the canonical lifecycle record. Existing generic related-item IDs remain compatibility pointers and are retained on migrated/new canonical RFIs when available. Drafting from a project change creates a bidirectional link, preserves original evidence, and records `requires_rfi`; resolving the change and closing the RFI remain separate human actions. See [RFI automation](rfi-automation.md).

## Dashboard, staleness, and Q&A

The dashboard reports open, unreviewed, assigned, overdue, high-priority, needs-information, resolved, closed, stale, and due-soon counts. Queue ranking is deterministic: priority, due date, update time, then stable ID. It is a review ordering, not a calibrated risk score.

Stale comparisons mark linked project changes without deleting history. Regeneration reruns deterministic comparison and register admission; stable evidence identities reuse records while changed findings remain reviewable. Operational Q&A labels answers as project-team records and names the source comparison. Human notes are never presented as original design requirements.

## Notifications

Notifications enter a local idempotent outbox. Payload fields are restricted to concise workflow metadata. The no-op and test adapters do not contact external systems. There is no email, Slack, Teams, SMS, or push delivery.

## Limitations

- No authentication or authorization; the API is development-only.
- No external notifications or construction-platform integrations.
- Related workflow records are internal drafts only.
- No automatic confirmation of cost, schedule, scope, safety, or quality impact.
- No background queue, web frontend, OCR, or drawing vision.
- Assignment suggestions and workflow classification require human confirmation.
- Regeneration reconciliation is deterministic and conservative; ambiguous semantic matches need review.
