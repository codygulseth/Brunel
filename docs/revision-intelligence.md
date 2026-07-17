# Revision Intelligence

Drawing comparison follows the same conservative evidence principles at sheet, index, text, and reference level. Native text remains distinct from OCR. Content changes not explained by extracted text are reported as visual or unparsed content requiring human review.

Revision Intelligence compares text-extractable document revisions, preserves evidence for every finding, and produces a reviewable construction change report. It supports specifications, minutes, RFIs, submittals, narrative drawings, text-based drawing PDFs, schedules, manuals, exhibits, and commissioning records.

## System flow

```text
Old revision + New revision
  -> Revision validation -> Comparability assessment
  -> Content normalization -> Section and block alignment
  -> Deterministic difference detection
  -> Construction-aware classification -> Significance assessment
  -> Optional provider boundary -> Citation validation
  -> Saved comparison -> Markdown or JSON report
  -> Cited Q&A and human review
```

Explicit document-family, sequence, and supersession metadata are authoritative. When metadata is incomplete, Brunel uses conservative title, filename, and type similarity and labels the relationship inferred. Cross-project comparisons fail closed; unrelated same-project documents require `--force` and carry warnings.

Normalization changes Unicode and whitespace only for matching. Every block retains untouched source text, document ID, page, chunk, offsets, sheet, specification section, and citation. Exact identifiers and text align first; similarity handles modifications. Near-tied candidates remain ambiguous. Token diffs expose additions, removals, replacements, numeric changes, requirement strength, negation, responsibility, and approval state.

Versioned rules classify procurement, schedule, cost, safety, testing, commissioning, responsibility, approval, equipment, material, quality, contract, and numeric changes. Each signal records its rule and supporting text. Severity, evidence strength, and review state are separate. Potential implications are never confirmed impacts.

## CLI

```powershell
python -m app.cli ingest --project-id demo-project --file spec-r1.txt --document-type specification --document-family-id concrete-spec --revision 1 --revision-sequence 1
python -m app.cli revisions --project-id demo-project --document-family-id concrete-spec
python -m app.cli compare --project-id demo-project --old-document-id doc_old --new-document-id doc_new --output reports/spec-r1-to-r2.md
python -m app.cli comparison-list --project-id demo-project
python -m app.cli comparison-show --project-id demo-project --comparison-id cmp_id
python -m app.cli comparison-review --project-id demo-project --comparison-id cmp_id --change-id chg_id --status accepted --note "Confirmed by PM."
python -m app.cli ask --project-id demo-project --question "Did the concrete strength change?"
```

Saved records contain source hashes, configuration and rules versions, warnings, and provider metadata. Stable IDs derive from deterministic inputs. Generated comparison data and reports are ignored by Git.

## Privacy and limitations

Comparison runs locally. Model assistance is disabled in the CLI unless an application adapter injects a provider; an unavailable or failing optional provider produces a warning and preserves the deterministic result. Providers receive validated findings rather than unrestricted project storage. No API keys or full source documents are logged. Results remain project-scoped.

There is no OCR, raster comparison, CAD/BIM parsing, graphical change clouding, or proprietary integration. PDF extraction controls quality; tables can lose visual structure; moved content can be ambiguous. Significance is decision support, not a substitute for contractual interpretation, licensed design judgment, safety authority, or professional review.

Operational review is implemented separately in `change_workflow`. Revision findings remain immutable evidence of document changes; project changes add assignments, dispositions, notes, links, resolution, and audit without rewriting the source comparison.
