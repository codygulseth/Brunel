# Development API

Start the canonical unauthenticated development API with `python -m app.api`. OpenAPI is available at `/docs` and `/openapi.json`; health and version endpoints are `/health` and `/version`.

Endpoints provide bounded project-change listing/filtering, dashboard and review queue, register generation, change retrieval, assignment, controlled transitions, dispositions, notes, audit history, workflow links, related drafts, and notification outbox inspection. All record access is project-scoped. `X-Actor-ID`, `X-Actor-Name`, and `X-Correlation-ID` may identify local audit context; these headers are not authentication.

This API must not be exposed to untrusted networks. Authentication, authorization, role checks, rate limits, tenant isolation, and deployment hardening are required before production use.
