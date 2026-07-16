# Document Ingestion

Brunel's Project Knowledge Engine begins with a deterministic ingestion pipeline. Its job is to turn a supported local file into validated, traceable internal records that future retrieval and question-answering systems can consume.

## Architecture flow

```text
File
  -> Loader
  -> Extractor
  -> Metadata normalization
  -> Page records
  -> Deterministic chunker
  -> Local repository
  -> Future retrieval layer
```

1. `LocalFileLoader` validates the path and extension, reads source bytes, and calculates a SHA-256 content hash.
2. A registered extractor creates `DocumentPage` records. PDF extraction happens independently for each page; TXT and Markdown are represented as one page.
3. `ConservativeMetadataExtractor` retains explicit construction metadata. It may retain an explicit Markdown H1 as the title, but does not guess revisions, dates, sheet numbers, specification sections, or document types.
4. `DeterministicTextChunker` chunks each page separately using configurable character size and overlap. It never merges pages.
5. `JsonDocumentRepository` atomically stores the source record, pages, chunks, and citations behind a repository interface.

## Internal records

- `Project` identifies the project knowledge boundary.
- `SourceDocument` records file identity, type, metadata, source path, ingestion time, content hash, and optional parent version.
- `DocumentPage` preserves the original page number, extracted text, construction locators, and page warnings.
- `DocumentChunk` stores a page-bound text span with stable offsets and identity.
- `CitationReference` supplies document name, page, optional sheet number, optional specification section, chunk ID, and source location.
- `IngestionResult` reports page/chunk counts, warnings, and the local storage location.

Document IDs are derived from project ID, original filename, and source content hash. Chunk IDs are derived from document ID, page number, offsets, and chunk content. Re-ingesting an unchanged file with unchanged chunking settings therefore produces stable document and chunk IDs. The ingestion timestamp is intentionally not part of identity.

## Running the CLI

```powershell
python -m app.cli ingest --project-id demo-project --file .\path\to\document.pdf
```

Example with explicit construction metadata:

```powershell
python -m app.cli ingest `
  --project-id demo-project `
  --file .\path\to\E-101.pdf `
  --document-type drawing `
  --title "Electrical Plan" `
  --revision "2" `
  --revision-date "2026-07-16" `
  --sheet-number "E-101"
```

The CLI prints the stable document ID, page/chunk counts, storage location, and extraction warnings. Failures return a nonzero exit code with a concise message.

## Traceability rules

- Source page boundaries and page numbers are never discarded.
- Missing metadata remains null or `unknown`; Brunel does not invent it from ambiguous filenames.
- Every non-empty chunk contains a citation reference.
- One empty or damaged PDF page records a warning and does not necessarily stop other pages.
- Uploaded documents and generated ingestion data are excluded from Git.

## Current limitations

- PDF extraction uses the embedded text layer. There is no OCR.
- Image-only drawings are retained as page records with warnings but yield no chunks.
- The system does not interpret drawing geometry, title blocks, schedules, spreadsheets, or scanned handwriting.
- TXT and Markdown input must be UTF-8.
- Local JSON storage is intended for development and evaluation, not concurrent production workloads.
- There is no access-control, malware-scanning, retention, semantic search, embedding, reranking, or LLM layer yet.

OCR and drawing understanding are deferred because they require separate quality evaluation, page-image processing, geometry-aware citations, and careful handling of title blocks, details, callouts, and revisions. Adding them prematurely would weaken Brunel's source-traceability guarantees.
