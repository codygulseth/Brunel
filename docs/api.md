# Development API

Start the canonical unauthenticated development API with `python -m app.api`. OpenAPI is available at `/docs` and `/openapi.json`; health and version endpoints are `/health` and `/version`.

Endpoints provide bounded project-change listing/filtering, dashboard and review queue, register generation, change retrieval, assignment, controlled transitions, dispositions, notes, audit history, workflow links, related drafts, and notification outbox inspection. All record access is project-scoped. `X-Actor-ID`, `X-Actor-Name`, and `X-Correlation-ID` may identify local audit context; these headers are not authentication.

This API must not be exposed to untrusted networks. Authentication, authorization, role checks, rate limits, tenant isolation, and deployment hardening are required before production use.

## RFI routes

The same API includes `GET/POST /projects/{project_id}/rfis`, `GET/PATCH /projects/{project_id}/rfis/{rfi_id}`, drafting from a project change, submit-review/review/issue, response and response-analysis, impact, controlled transition, close/reopen, audit, export, project log/dashboard, and `POST /projects/{project_id}/rfi-questions`. Listing supports bounded pagination and operational filters. Responses remove internal `source_location` values while retaining document, page, and chunk citation identity.

RFI routes delegate all lifecycle rules to `RFIService`. HTTP 404 represents a missing project-scoped record; domain conflicts return 409; request validation returns 422. API-created records can use `X-Actor-ID` and `X-Actor-Name` for audit attribution. See [RFI automation](rfi-automation.md).
