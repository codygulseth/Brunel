# ADR 0002: Isolate the legacy Project Engineer prototype

## Status

Accepted, 2026-07-17.

## Context

`src/ai_project_engineer` is an early FastAPI/SQLAlchemy organization-and-responsibility prototype. Brunel's canonical architecture now lives in the top-level domain packages, uses Pydantic boundary models, protocol-based repositories, deterministic services, and adapters under `app`. Several compatibility tests still import the prototype directly, so deleting it in this feature would remove verified behavior unrelated to revision review.

## Decision

The prototype remains temporarily as an explicitly deprecated compatibility boundary. It is not a production path for new Brunel capabilities. `change_workflow`, `revision_intelligence`, ingestion, retrieval, and canonical CLI/API code must not import `ai_project_engineer`. New tests enforce this boundary. The new API is `app.api`; the legacy application is not mounted or composed into it.

## Consequences

Existing prototype tests continue to pass while migration can be planned separately. Future contributors must add capabilities to canonical top-level modules and must not extend `src/ai_project_engineer`. Removal requires migrating or retiring its registry tests, templates, seed data, packaging entries, and README compatibility instructions in one deliberate change.
