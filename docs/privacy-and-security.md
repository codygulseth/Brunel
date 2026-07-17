# Privacy and Security

Brunel treats documents, comparisons, and workflow records as confidential project information. Canonical services are local by default. No notification adapter delivers externally, no model call occurs unless explicitly enabled, and standard logs contain identifiers and counts rather than complete documents.

Repositories validate record identifiers, use atomic replacement, enforce project scoping, and keep generated data under ignored data roots. Workflow URLs accept HTTP(S) only. API pagination is bounded. Audit events are append-only through normal services and avoid source excerpts.

The development API has no authentication or authorization and must remain local. Production deployment requires identity, role- and project-based authorization, encrypted transport/storage, secrets management, retention policies, audit export controls, abuse protection, and security review.

RFI records may contain contract-sensitive questions and responses. HTTP serialization removes local filesystem source paths, notification payloads exclude evidence excerpts and response text, and generated forms/logs stay in ignored report directories. Official-response labels are explicit; Brunel does not convert internal notes into contract documents or send them to recipients. External model assistance is disabled by default and deterministic drafting requires no network.

Submittal records may contain proprietary product data, pricing-adjacent procurement information, design-team responses, and contract-sensitive deviations. HTTP output strips local source paths; notification payloads contain only operational metadata; generated packages, logs, and demo data remain in ignored roots. Attachment metadata never causes a file upload. Official dispositions are explicitly labeled and kept separate from project-team notes and Brunel inference. External model assistance, external notifications, procurement release, and schedule mutation are all disabled or human-controlled by default.
