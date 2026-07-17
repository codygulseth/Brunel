# Retrieval and Cited Project QA

Brunel answers project questions only from ingested project evidence. The baseline is deliberately local, deterministic, and inspectable.

## System flow

```text
User question
  -> Query normalization
  -> Project-scoped retrieval
  -> Evidence ranking
  -> Evidence assessment
  -> Grounded answer generation
  -> Citation validation
  -> Structured response
```

## Retrieval approach

`LocalProjectRetriever` combines four deterministic signals:

1. Coverage of meaningful normalized query terms
2. Capped term frequency
3. Exact query-phrase matching
4. Exact construction-identifier matching

The normalizer recognizes lightweight patterns for sheet numbers, specification sections, room numbers, RFIs, submittals, revisions, and similar discipline identifiers. Retrieval filters by project before scoring and can also filter document type, document ID, page, sheet, and specification section. Identical normalized chunk content is returned once.

This approach was selected because it is fast, dependency-light, deterministic, debuggable, and strong enough to establish retrieval and citation contracts. BM25, vector, hybrid, metadata-aware, and reranking implementations can later implement the same `Retriever` protocol.

## Grounded answering

The default `ExtractiveAnswerProvider` uses only retrieved chunks and quotes source text verbatim. `EvidenceAssessor` considers retrieval relevance, supporting chunks, exact identifiers, citation completeness, and materially relevant conflicting measurements or approval states. It returns descriptive levels: `strong`, `moderate`, `weak`, `insufficient`, or `conflicting`.

The orchestration service:

- returns “The provided project documents do not establish this” when retrieval is empty;
- marks incomplete support as `partially_answered`;
- presents materially relevant conflicts instead of choosing one source;
- rejects provider citations that were not retrieved;
- rejects quoted text absent from supplied evidence;
- constructs final excerpts directly from source chunks;
- fails safely if a provider errors or returns invalid structured output.

Citation excerpts are short exact substrings selected from the best matching source sentence. Each citation includes its stable ID, document ID, title and filename, page, optional sheet/specification references, chunk ID, source location, and excerpt.

## CLI

Ingest synthetic or authorized project content:

```powershell
python -m app.cli ingest --project-id demo-project --file .\sample.txt --document-type specification --specification-section "03 30 00"
```

Inspect ranked evidence:

```powershell
python -m app.cli search --project-id demo-project --query "generator pad concrete strength" --top-k 5
```

Ask a cited question:

```powershell
python -m app.cli ask --project-id demo-project --question "What concrete strength is required for the generator pad?"
```

Example local response:

```text
Answer: The provided project documents state: "Generator pad concrete shall have a minimum compressive strength of 4,000 psi at 28 days."
Status: answered
Evidence: strong
Sources retrieved: 1
[1] Synthetic Cast-in-Place Concrete [concrete-spec.txt] (page 1, spec 03 30 00)
    Generator pad concrete shall have a minimum compressive strength of 4,000 psi at 28 days.
```

## Provider replacement

Answer providers implement `GroundedAnswerProvider`. The optional OpenAI-compatible adapter receives an evidence-only prompt, requests JSON, validates `AnswerDraft`, and uses bounded retries. It is off by default. A local model adapter can implement the same `LanguageModelClient` without modifying retrieval or QA orchestration.

## Current limitations

- Scoring is a local lexical baseline, not calibrated relevance.
- Conflict detection covers common measurements and approval states, not full semantic contradiction.
- Extractive answers favor one directly supporting chunk and do not synthesize complex multi-document narratives.
- There are no embeddings, vector database, learned reranker, access-control layer, OCR, or drawing vision.
- Source freshness, supersession, and contractual precedence are not resolved automatically.

Embeddings and vector databases are deferred until a construction-specific evaluation set can measure whether they improve recall without weakening project isolation or citation precision. Future drawing intelligence will emit the same page/sheet-aware chunks and citation structures, allowing retrieval to include title-block, callout, detail, and geometry-derived evidence without changing the answer contract.

## Revision findings

Questions with revision intent first search saved findings within the requested project. Supported answers include the comparison ID, exact old/new excerpts, and original document/page/chunk citations. Summaries never replace source evidence, and no other project's finding is considered.

