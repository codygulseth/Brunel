# Drawing Intelligence Foundation

Brunel indexes construction drawing sets conservatively. A set revision is a canonical immutable `SourceDocument`; drawing analysis attaches sheet, title-block, index, reference, region, readability, OCR, validation, graph, and comparison records to canonical document/page IDs.

## Evidence and workflow

Native PDF text remains distinct from opt-in OCR. Visual coordinates use normalized 0–1 page space with a top-left origin; x increases right and y increases down. A region identifies where evidence was found and does not claim an exact graphical object was understood. Unknown metadata remains null and extracted candidates remain distinct from human-confirmed values.

`drawing-set-ingest` stores the PDF through canonical ingestion, renders each page through an adapter, assesses readability, identifies explicit sheet metadata, parses sheet lists, extracts explicit textual references, reconciles the index, builds a directed graph, and preserves validation issues. Render failures are page warnings rather than whole-set failures. Source revisions are immutable.

The parser recognizes explicit sheet, detail, section, elevation, schedule, diagram, continuation, and matchline text. Duplicate, missing, unindexed, title-conflicting, and unresolved-reference conditions remain available for human review.

Built-in right-side, bottom, and full-page fallback title-block templates are versioned. Explicit selection is authoritative; automatic fallback is marked for human review. Explicit keynote legends and labelled occurrences retain region citations. Sheet lineage uses exact identity first and reports possible renumbering for human review.

## OCR, API, CLI, and privacy

OCR is disabled by default. OCR blocks retain provider/version, confidence, and bounding boxes and never replace native text. Low-confidence results require confirmation. No external model, OCR, notification delivery, or file transfer occurs by default.

The unauthenticated development API exposes drawing-set registration/list/detail/analyze; sheet detail/review/reference/region; validation/graph/unresolved-reference; OCR; comparison/export; and search under `/projects/{project_id}`. Uploads accept PDF only and are limited to 50 MiB.

CLI commands are `drawing-set-ingest`, `drawing-set-list`, `drawing-set-show`, `drawing-set-analyze`, `drawing-sheet-list`, `drawing-sheet-show`, `drawing-metadata-review`, `drawing-index-show`, `drawing-validation`, `drawing-references`, `drawing-reference-graph`, `drawing-sheet-ocr`, `drawing-set-compare`, and `drawing-search`.

Drawing questions use `/drawing-ask` and the existing `ask` CLI. Answers identify their evidence type and return page/region citations. Unsupported graphical questions return an explicit limitation instead of an inference.

## Limitations

Brunel does not perform professional design review, understand all graphical content, generate redlines, perform quantity takeoffs, detect clashes, parse CAD/BIM, approve drawings, or create/issue RFIs automatically. Visual-only changes remain unexplained. Visual-region citations identify evidence locations, not graphical meaning.
