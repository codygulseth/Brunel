# RFI Automation

Brunel's canonical `rfi` module manages internal requests for information from evidence-backed draft through closure. It is a deterministic construction workflow, not an external document-control system. Every draft requires human review, and no email or external notification is sent.

## Lifecycle and authority

The explicit lifecycle is `draft -> pending_internal_review -> revisions_required | approved_for_issue -> issued -> acknowledged | under_review | response_received -> clarification_required | answered -> resolved | closed`. Void, supersede, and reopen operations require reasons. Issue requires an approved draft, cited evidence, responsible design party, and required response date. Closure requires a resolution summary and resolved or closed linked project changes.

Official responses must be explicitly recorded as `official`; draft and informal responses never become official implicitly. Response analysis is conservative and produces labeled potential-impact inferences. It never closes an RFI or resolves a project change. A human performs those transitions.

## Evidence-backed drafting

`RFIService.draft_from_change` reads a project-scoped canonical project change and retains its old/new source citations. `DeterministicRFIDrafter` produces a concise draft without a model. An optional `RFIDraftProvider` may improve wording, but its output remains subject to citation and quality validation; a provider failure retains the deterministic draft.

The deterministic validator flags missing evidence, missing document identity, unsupported numeric claims, multiple questions, vague or accusatory wording, missing assignments/dates, and excessive length. Duplicate detection checks the same project change, shared citations/references, and question similarity. It only recommends review and never merges records automatically.

## Numbering, revisions, and persistence

`RFINumberingService` abstracts project-scoped sequential numbers. The local adapter uses stable prefixes and digit lengths without reusing voided values. A draft-only administrative override requires a reason and creates an audit event; numbers are immutable once review begins.

Each wording revision retains the complete text, evidence, author, timestamp, change summary, approval state, and content hash. JSON records use a schema version and optimistic version checks. Atomic local writes live below `BRUNEL_DATA_DIRECTORY/rfi`; generated exports belong under `reports/rfis` and are ignored by Git.

## Project-change integration and legacy placeholder

The canonical `rfi.RFI` is the source of truth. The earlier generic `change_workflow.RelatedItem` with `WorkflowType.RFI` remains a compatibility pointer only. New RFI drafts retain a `legacy_related_item_id` when one exists, create a canonical workflow link back to the project change, preserve evidence, and set the change disposition to `requires_rfi`. Migration is therefore additive: existing placeholder identifiers remain traceable while all lifecycle data is stored in `rfi`.

An official response can suggest that a linked change may be resolvable, but the project change is updated only through its own human-controlled service. Closing an RFI never deletes the project change.

## Impacts, logs, and dashboards

Impact records distinguish `confirmed`, `likely`, `possible`, `unknown`, and `not_applicable`. Cost, schedule, scope, procurement, quality, safety, testing, commissioning, owner-decision, and field-coordination impacts are recorded as human assessments with optional evidence. Brunel does not calculate money or time and does not promote a potential impact to confirmed.

The project log supports project-safe search, status, discipline, priority, reviewer, responsible party, overdue/open state, project-change, document-reference, and date filters. Dashboard metrics are operational counts and aging summaries—not a calibrated risk model. Markdown/JSON RFI forms and Markdown/CSV logs are available.

## API and CLI

The unauthenticated development API exposes project-scoped RFI CRUD/revision routes, review, issue, response, impact, transition, close/reopen, audit, log, dashboard, export, and operational question endpoints. It inherits correlation IDs and structured error handling from `app.api`; internal filesystem source locations are removed from HTTP output. See `docs/api.md` for the route list.

Representative CLI flow:

```powershell
python -m app.cli rfi-draft --project-id demo-project --change-id change-id --responsible-party "Electrical Engineer" --required-date 2026-08-15
python -m app.cli rfi-submit-review --project-id demo-project --rfi-id rfi-id --reviewer-id electrical-pm
python -m app.cli rfi-review --project-id demo-project --rfi-id rfi-id --reviewer-id electrical-pm --decision approved
python -m app.cli rfi-issue --project-id demo-project --rfi-id rfi-id
python -m app.cli rfi-response --project-id demo-project --rfi-id rfi-id --responding-party Engineer --response-file response.md
python -m app.cli rfi-dashboard --project-id demo-project
```

Run the complete synthetic electrical scenario (generated local data only):

```powershell
python -m app.cli rfi-demo --project-id synthetic-rfi-demo
```

## Notifications and audit

Assignments, status changes, and official responses queue sanitized records in the existing local notification outbox. Payloads contain title/status/date metadata, not confidential excerpts. `NoOpNotificationAdapter` remains the default; no external delivery occurs. Creation, numbering, revisions, review decisions, transitions, responses, impacts, and assignments have append-only audit events.

## Current limitations

- Internal records only; no Procore, Autodesk Construction Cloud, email, or document-control integration.
- No authentication, authorization, or production database.
- No PDF RFI form export.
- Optional model assistance has an interface but no enabled provider by default.
- Response analysis uses conservative deterministic indicators and needs human confirmation.
- Local numbering is atomic where practical but is not a distributed lock service.
