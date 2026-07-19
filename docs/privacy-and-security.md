# Privacy and Security

Meeting records can contain sensitive project and personnel information. Source text remains in canonical local storage, audit metadata excludes full transcripts, and the default feature performs no model egress, email delivery, calendar access, conferencing access, or external notification delivery.

Drawing PDFs, renders, native text, OCR blocks, and reports remain local by default. Generated artifacts are excluded from Git. Audit/log records contain identifiers and summaries rather than full drawing content. No OCR/model egress occurs in the default implementation.

Brunel treats documents, comparisons, and workflow records as confidential project information. Canonical services are local by default. No notification adapter delivers externally, no model call occurs unless explicitly enabled, and standard logs contain identifiers and counts rather than complete documents.

Repositories validate record identifiers, use atomic replacement, enforce project scoping, and keep generated data under ignored data roots. Workflow URLs accept HTTP(S) only. API pagination is bounded. Audit events are append-only through normal services and avoid source excerpts.

The development API has no authentication or authorization and must remain local. Production deployment requires identity, role- and project-based authorization, encrypted transport/storage, secrets management, retention policies, audit export controls, abuse protection, and security review.

RFI records may contain contract-sensitive questions and responses. HTTP serialization removes local filesystem source paths, notification payloads exclude evidence excerpts and response text, and generated forms/logs stay in ignored report directories. Official-response labels are explicit; Brunel does not convert internal notes into contract documents or send them to recipients. External model assistance is disabled by default and deterministic drafting requires no network.

Submittal records may contain proprietary product data, pricing-adjacent procurement information, design-team responses, and contract-sensitive deviations. HTTP output strips local source paths; notification payloads contain only operational metadata; generated packages, logs, and demo data remain in ignored roots. Attachment metadata never causes a file upload. Official dispositions are explicitly labeled and kept separate from project-team notes and Brunel inference. External model assistance, external notifications, procurement release, and schedule mutation are all disabled or human-controlled by default.

Submittal attachment intelligence accepts only configured local paths, enforces an input-root boundary, rejects executable extensions, applies a file-size limit, hashes content, and stores immutable binaries below `BRUNEL_DATA_DIRECTORY`. API and report serialization removes local storage and source paths while retaining document/page/chunk citation identity. PDF, TXT, and Markdown extraction runs locally through canonical ingestion; other allowed formats remain metadata-only and archives are never expanded. OCR, CAD/BIM interpretation, external model transfer, and external notification delivery are disabled or absent.

Procurement records may contain commercially sensitive supplier, quote, authorization, and forecast references. Standard API responses and local outbox payloads exclude commercial amounts, credentials, and internal paths. Commercial values are human-entered; Brunel performs no purchasing, payment, supplier scoring, external delivery, automatic release, or schedule modification.

Imported schedule files and normalized records remain under ignored local storage. API output returns citations and normalized facts without internal storage paths. Audit and notification payloads use identifiers and summaries rather than full schedule records. The development API is unauthenticated and must remain local; no write-back, external model call, or external notification delivery exists by default.

Daily reports and media may contain sensitive project and personnel information. Brunel defaults to aggregate crew records, avoids unnecessary names and medical information, performs no facial recognition or biometric processing, stores source files locally under ignored roots, and sends neither report content nor notifications externally.
