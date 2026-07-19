# Primavera P6 Schedule Adapter

## Architecture

The P6 adapter is a vendor boundary over Brunel's existing Integration Adapter Framework and Schedule Intelligence Foundation. `PrimaveraP6Adapter` declares transport capabilities and performs safe parsing. `PrimaveraP6Service` coordinates explicit mapping and delegates immutable admission to `ScheduleIntelligenceService`. It does not persist a parallel schedule, identity, audit, notification, synchronization, or approval model.

```text
XER / P6 XML
  -> versioned P6 adapter + safe parser
  -> canonical import session + immutable raw external record
  -> explicit P6-project mapping
  -> canonical immutable schedule revision
  -> schedule quality / lineage / comparison / retrieval

Reviewed Brunel evidence
  -> canonical export proposal
  -> validation + explicit human approval
  -> deterministic in-memory test execution only
  -> external-state reconciliation
```

The adapter manifest is versioned at `1.0.0`. Connections default to read-only even though the adapter advertises a narrowly bounded write workflow. `write_enabled` must be explicitly set, an external-write approver must be named, and only `test_in_memory` can execute in this release.

## Connections and transports

Connections use canonical organization/project scoping and secret references. Configuration supports `transport`, optional encoding, external environment/tenant labels, timezone assumptions, and an explicitly confirmed external project ID. Credentials and tokens are never configuration values.

Supported modes:

- `xer_file`: deterministic XER discovery and import.
- `p6_xml_file`: namespace-tolerant XML discovery and import.
- `test_in_memory`: deterministic approved-export tests; no network access.
- `future_api`: declared extension point that fails connection testing as not implemented.

Future P6 EPPM REST, P6 Professional database, Primavera Cloud, secure exchange, and enterprise repository transports must implement the existing adapter interface. Brunel does not invent or claim undocumented Oracle behavior.

## Parsing and source preservation

The XER reader handles `%T`, `%F`, `%R`, `%E`, blank values, multiple projects, common encoding fallback, unknown fields, unknown tables, malformed row warnings, and partial parsing. It recognizes project, WBS, task, predecessor, calendar, activity code, UDF, resource/assignment, memo, issue, currency, and related metadata tables. Unsupported tables remain summarized in immutable raw metadata and never fail an otherwise admissible import.

The XML reader is namespace tolerant and accepts missing optional elements. It rejects DTD/entity declarations, malformed XML, and sources over the parser size limit. Unknown optional elements do not become authoritative core fields.

The integration repository retains an immutable raw-record envelope with connection, file path/name, format, content hash, parser version, project IDs, import session, warnings, authorization scope, and external version. Canonical schedule admission copies the original file into revision-scoped immutable source storage. Reimports with the same project/content hash are idempotent; changed content at the same data date creates a distinct revision.

## Normalization and provenance

P6 object IDs and editable activity IDs remain separate. Activities preserve original and remaining duration, status, dates, progress, float, constraint fields, calendar/WBS references, codes, UDF/vendor fields, and source-row/table evidence in `source_fields`. WBS, calendars, and relationships enter canonical schedule records. Relationship object references are mapped to activity IDs only when deterministic. Missing or conflicting references remain quality findings rather than being silently repaired.

Imported source dates/float, Brunel calculations, human-confirmed evidence, and proposed updates remain distinct. Resources, assignments, costs, expenses, baselines, notes, and unknown vendor fields are preserved where available, but the foundation does not claim full resource/cost/baseline normalization. Restricted commercial data must remain access-controlled and is not used to infer productivity.

Project mapping requires exact configuration or explicit human confirmation. Name similarity alone never maps a P6 project. Canonical external identity mappings link the admitted schedule revision back to the immutable P6 raw record. Regressed data dates create reviewable integration conflicts. Schedule comparison and quality assessment use the canonical deterministic policies and never characterize findings as contractual noncompliance.

## Export proposals and human authority

Initial proposal fields are limited to actual start, actual finish, percent complete, remaining duration, expected finish, and a reviewed Brunel reference note/UDF. Relationship, constraint, calendar, resource, cost, baseline, create, delete, and WBS-move writes are rejected.

Validation requires an active explicitly write-enabled connection, `test_in_memory` transport, confirmed project and activity object mappings, a current source revision, expected external version, evidence, rationale, authorized actor, supported field, and idempotency key. Exact payload approval is stored by the canonical framework. Payload changes invalidate approval; expiration or external-version mismatch blocks execution. Execution is idempotent and always followed by value-level reconciliation. A transport success alone is not success.

Brunel never independently modifies P6; changes dates, duration, percent complete, relationships, constraints, calendars, resources, costs, baselines, status date, WBS, or activities; applies or publishes schedules; or determines delay, critical-path entitlement, responsibility, or contractual schedule compliance. Humans retain every schedule decision. No external communication, model call, or notification delivery occurs by default.

## API, CLI, dashboard, and Q&A

Project-scoped `/organizations/{organization_id}/projects/{project_id}/p6` endpoints expose capabilities, discovery, mapping, import, revisions, comparison, quality, conflicts, search, export proposal lifecycle, reconciliation, dashboard, and cited questions. Generic integration endpoints create and test connections. Responses never contain secret values.

The nested CLI starts with:

```powershell
python -m app.cli p6 adapter-info
python -m app.cli p6 create-connection --organization-id org --project-id project --transport xer_file
python -m app.cli p6 discover-projects --organization-id org --project-id project --connection-id connection_id --file schedule.xer
python -m app.cli p6 map-project --organization-id org --project-id project --connection-id connection_id --external-project-id 10
python -m app.cli p6 import-xer --organization-id org --project-id project --connection-id connection_id --file schedule.xer
```

Dashboard and Q&A combine canonical integration and schedule records. Answers cite the P6 connection, external project, source revision, data date, external version, source file, import session, and evidence type. Imported values and Brunel-calculated comparisons are explicitly distinguished; conflicts are preserved.

## Known limitations

- No production Oracle API, database, Primavera Cloud, or secure-file write transport exists.
- P6 XML/XER exports vary by Oracle version and organization customization; unsupported fields remain raw evidence.
- Complex calendar work patterns, resource/cost controls, baseline semantics, notebook formatting, cross-project relationships, and every P6 version are not fully normalized.
- File imports do not provide vendor-side pagination, webhooks, or updated-since cursors; content hashes provide deterministic incremental identity.
- The API is still the repository's unauthenticated development API; service-layer organization/project and actor authorization guards remain enforced.
