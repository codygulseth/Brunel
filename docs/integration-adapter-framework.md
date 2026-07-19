# Integration Adapter Framework

Brunel integrations use explicitly registered, versioned adapters with machine-readable capability manifests. Adapters default to read-only. Vendor payloads remain immutable raw records, then pass through deterministic field-level normalization with durable external citations before a human admits proposals through canonical domain services.

Connections are organization/project scoped. Credentials are represented only by secret references; no password, token, private key, refresh token, or client secret belongs in canonical records, APIs, CLI output, logs, or audit payloads. Connection tests must be non-mutating.

Incremental sessions commit cursors only on their defined completion state. External record/version hashes provide duplicate-safe replay. External deletion creates preserved evidence and a reviewable conflict; it never deletes Brunel history.

Every external write begins as a versioned export proposal. Execution requires an active explicitly write-enabled connection, adapter capability validation, source evidence, explicit human approval, an unchanged payload hash, unexpired approval, expected-version handling, idempotency, audit, and reconciliation. An HTTP success alone is not reconciliation.

Reference adapters are deterministic fixtures only: local-file and generic JSON adapters are read-only; the generic in-memory writer is test-only. The separately documented P6 adapter provides production-oriented file parsing and canonical admission, but external execution remains test-only. No Oracle API, Procore, ACC, SharePoint, ERP, or email transport is implemented.

Adapters may never bypass project authorization or domain services, modify canonical records directly, execute unapproved writes, expose credentials, resolve conflicts silently, delete Brunel history, treat external status as unquestioned authority, or send external communications without explicit human authorization.
