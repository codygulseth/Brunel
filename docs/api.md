# Development API

Meeting operations add project-scoped meeting/series creation, safe record upload, deterministic analysis, candidate review, action and decision registers, minutes review/issue, comparison, dashboards, search, audit, and cited Q&A. The API remains unauthenticated development infrastructure and never distributes minutes externally.

Drawing Intelligence adds project-scoped drawing-set upload/list/detail/analyze, sheet metadata review, references, visual regions, validation, graph, controlled OCR, comparisons, search, cited drawing Q&A, audit, and local outbox endpoints. Uploads are PDF-only and capped at 50 MiB. The API remains unauthenticated development infrastructure.

Start the canonical unauthenticated development API with `python -m app.api`. OpenAPI is available at `/docs` and `/openapi.json`; health and version endpoints are `/health` and `/version`.

Endpoints provide bounded project-change listing/filtering, dashboard and review queue, register generation, change retrieval, assignment, controlled transitions, dispositions, notes, audit history, workflow links, related drafts, and notification outbox inspection. All record access is project-scoped. `X-Actor-ID`, `X-Actor-Name`, and `X-Correlation-ID` may identify local audit context; these headers are not authentication.

This API must not be exposed to untrusted networks. Authentication, authorization, role checks, rate limits, tenant isolation, and deployment hardening are required before production use.

## RFI routes

The same API includes `GET/POST /projects/{project_id}/rfis`, `GET/PATCH /projects/{project_id}/rfis/{rfi_id}`, drafting from a project change, submit-review/review/issue, response and response-analysis, impact, controlled transition, close/reopen, audit, export, project log/dashboard, and `POST /projects/{project_id}/rfi-questions`. Listing supports bounded pagination and operational filters. Responses remove internal `source_location` values while retaining document, page, and chunk citation identity.

RFI routes delegate all lifecycle rules to `RFIService`. HTTP 404 represents a missing project-scoped record; domain conflicts return 409; request validation returns 422. API-created records can use `X-Actor-ID` and `X-Actor-Name` for audit attribution. See [RFI automation](rfi-automation.md).

## Submittal routes

Project-scoped routes cover specification requirement extraction and candidate review; register creation, listing, retrieval, assignment, procurement dates, and controlled transitions; package creation, completeness, internal review, issue, official/informal responses, conservative response analysis, resubmittals, and staleness; human procurement release; and logs, dashboard, audit, export, and operational Q&A.

Procurement Intelligence adds project-scoped candidate extraction/review, item and lifecycle operations, lead times, date plans, dependencies, milestones, forecasts, readiness, human authorization, delivery, staleness, audit, register, dashboard, exposure, plan snapshots, and comparisons. These unauthenticated development routes never place orders, send notifications, or modify schedules.

Schedule Intelligence adds immutable schedule import, revision/activity reads, quality analysis, criticality views, milestones, look-ahead, lineage review, deterministic comparison, workflow links, synchronization proposals, dashboard, register, and search. No schedule write-back endpoint exists; accepted synchronization proposals remain explicit human-reviewed proposals unless a separate canonical downstream command is invoked.

Daily Reports and Field Intelligence adds project-day/report creation, local structured ingestion, immutable revisions, proposed observation review, deterministic draft/review/issue, field dashboards, search, and cited questions. It has no automatic schedule progress, workflow closure, external distribution, or contractual-impact endpoint.

All workflow rules remain in `SubmittalService`. Missing records return 404, lifecycle conflicts return 409, and malformed requests return 422. Citation output keeps document/page/chunk identity but strips `source_location`. The API never uploads a package externally, sends a notification, calls a model by default, determines technical compliance, or releases procurement automatically. See [Submittal automation](submittal-automation.md).

## Submittal attachment intelligence routes

Project-scoped package routes register/list attachments, run attachment analysis, summarize evidence, list and review proposed compliance mappings, compare package revisions, check/acknowledge staleness, and read attachment audit history. Project attachment routes retrieve immutable metadata/extractions, search cited content, and answer cited questions.

`POST /projects/{project_id}/submittal-packages/{package_id}/attachments` accepts an allowed local input path in this development adapter; it is not an Internet upload endpoint. API serialization strips `storage_reference`, `source_path`, and `source_location`. Content analysis is deterministic and local by default. See [Submittal Attachment Intelligence](submittal-attachment-intelligence.md).
