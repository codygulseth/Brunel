# Privacy and Security

Brunel treats documents, comparisons, and workflow records as confidential project information. Canonical services are local by default. No notification adapter delivers externally, no model call occurs unless explicitly enabled, and standard logs contain identifiers and counts rather than complete documents.

Repositories validate record identifiers, use atomic replacement, enforce project scoping, and keep generated data under ignored data roots. Workflow URLs accept HTTP(S) only. API pagination is bounded. Audit events are append-only through normal services and avoid source excerpts.

The development API has no authentication or authorization and must remain local. Production deployment requires identity, role- and project-based authorization, encrypted transport/storage, secrets management, retention policies, audit export controls, abuse protection, and security review.
