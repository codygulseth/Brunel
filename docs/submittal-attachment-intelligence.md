# Submittal Attachment Intelligence

Brunel's attachment-intelligence foundation turns local submittal files into traceable submitted evidence. It supplements the canonical submittal workflow; it does not replace the architect/engineer, approve products, determine design compliance, release procurement, modify schedules, or contact an external system.

## Scope and authority

The module records what a submitted attachment explicitly states and where it states it. It keeps four concepts separate:

1. A specification requirement is source evidence extracted from an ingested specification.
2. A submitted attachment fact is source evidence extracted from a package attachment.
3. A Brunel mapping, mismatch, conflict, or possible-deviation indicator is a deterministic proposal requiring human review.
4. An official design-team disposition is an explicit existing submittal workflow record and is never inferred from attachment content.

Completeness asks whether required, readable content is present. It does not answer whether a design or product technically complies.

## Architecture

`AttachmentIngestionService` validates the input root, filename, extension, and size; computes SHA-256; writes an immutable binary revision through `AttachmentFileStore`; and routes supported PDF/TXT/Markdown content through canonical `DocumentIngestionService`. Allowed but unsupported Office, image, BIM, CAD, and archive formats retain metadata with an `unsupported` readability state and cannot satisfy a mapping. Executable formats are blocked.

`AttachmentContentExtractor` deterministically assesses readability and extracts document classification, manufacturer/product/model candidates, ratings, dimensions, warranty terms, and explicit specification/drawing/equipment/RFI/standard references. Every extracted field points to an attachment revision and canonical document/page/chunk citation. Unknown or conflicting text stays unknown or conflicting.

`PackageAttachmentAnalysisService` assembles immutable package evidence sets from attachment revision hashes, extraction IDs, requirement IDs, and versioned policy identifiers. It identifies required types that lack readable content, package/reference mismatches, cross-attachment value conflicts, and explicit text differences that may be deviations. It then creates proposed requirement mappings with `strong`, `moderate`, `weak`, `insufficient`, or `conflicting` evidence descriptions.

Mappings remain separate mutable human-review records so reviewers can confirm, modify, reject, or request information without rewriting the original extraction or evidence snapshot. Reviews identify the reviewer, time, note, confirmed status, and any cited evidence adjustment.

`PackageRevisionComparisonService` compares saved evidence sets across package revisions. It reports added, removed, replaced, and modified attachment content plus changed models, ratings, dimensions, warranties, requirement mapping states, and conflicts. Old and new cited evidence is retained. Repeating the same comparison reuses its deterministic identity.

## Persistence and staleness

The local adapter stores binaries separately from JSON domain records. Attachment aggregates use optimistic concurrency; extraction results, evidence sets, comparisons, and staleness records are immutable append records. List operations skip corrupt files and always filter by project. Audit events are append-only in the canonical submittal repository.

When attachment evidence changes after internal review, Brunel preserves the prior evidence set and official disposition, marks review currency stale, and requires renewed human review. A local notification-outbox request may be queued for an assigned reviewer; there is no external delivery adapter. Acknowledgment records awareness but does not approve content.

## Search, Q&A, and exports

Attachment search ranks explicit manufacturer, product, model, attribute, reference, and excerpt terms within a project and optional package. Package Q&A uses the current saved evidence set, returns attachment citations, and optionally includes related specification citations. If evidence does not establish an answer, Brunel says so. Answers explicitly distinguish submitted facts, Brunel extraction, professional compliance, and official disposition.

Markdown and JSON exports include hashes, revision identities, readability, proposed mappings, specification citations, attachment citations, and unresolved exceptions. They omit internal binary and source paths.

Representative commands:

```powershell
python -m app.cli submittal-attachment-add --project-id project-a --package-id package-id --file .\product-data.pdf --declared-type product_data --role manufacturer_data
python -m app.cli submittal-attachment-list --project-id project-a --package-id package-id
python -m app.cli submittal-attachment-analyze --project-id project-a --package-id package-id
python -m app.cli submittal-attachment-mappings --project-id project-a --package-id package-id
python -m app.cli submittal-attachment-review-mapping --project-id project-a --package-id package-id --requirement-id requirement-id --reviewer-id reviewer --confirmation confirmed
python -m app.cli submittal-attachment-compare --project-id project-a --package-id package-id --old-revision 1 --new-revision 2
python -m app.cli submittal-attachment-search --project-id project-a --package-id package-id --query "BSE-MSB-200 85 kA"
python -m app.cli submittal-attachment-ask --project-id project-a --package-id package-id --question "What model and rating were submitted?"
python -m app.cli submittal-attachment-export --project-id project-a --package-id package-id --format markdown
```

Run `python -m app.cli submittal-attachment-demo` for a fully synthetic switchboard example with two package revisions, a human mapping review, cited Q&A, comparison, and Markdown export.

## Current limitations

- No OCR, table-cell reconstruction, drawing/BIM interpretation, image analysis, or encrypted-PDF recovery.
- Deterministic extraction targets explicit labels and construction patterns; complex product families and contextual tables need human review.
- Similar-but-not-identical duplicate detection is conservative; exact hash duplicates are definitive, while semantic duplicate decisions remain human-controlled.
- The development API accepts configured local paths and has no authentication or production upload quarantine.
- JSON storage provides local atomicity and optimistic checks, not distributed transactions or tenant-grade authorization.
- Optional model assistance is not used by this foundation. If added later, provider output must cite accepted source chunks and fail closed to deterministic results.
