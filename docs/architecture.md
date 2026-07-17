# Architecture

Brunel is an elite AI construction copilot designed around evidence, modularity, and human authority.

## Approach

Brunel uses a modular monolith initially. Each capability owns a coherent contract and can evolve internally without forcing distributed-system complexity. Modules communicate through typed interfaces and Pydantic boundary models. Infrastructure and frameworks depend inward on these contracts.

```text
Delivery adapters (future FastAPI, CLI, workers)
                         │
                  app/bootstrap.py
                         │
          workflows ─ agents ─ tools
              │          │       │
 document_processing ── rag ── prompts
              │          │
           models     storage interfaces
                         │
          adapters (database, files, model providers)
```

## Package responsibilities

- `app` is the composition root. Future FastAPI routes, CLI commands, and workers obtain dependencies here.
- `core` contains small cross-cutting primitives: dependency registration and logging. It must not absorb construction domain logic.
- `models` contains shared identifiers and evidence primitives. Feature-specific models remain with their feature.
- `document_processing` defines intake and parsing boundaries. Format-specific implementations come later.
- `rag` defines citation-aware retrieval without choosing a vector database or model.
- `revision_intelligence` owns lineage, comparability, normalization, alignment, token diffs, explainable classification, significance, saved findings, and rendering.
- `change_workflow` owns operational admission, assignments, transitions, dispositions, notes, links, draft actions, audit, dashboard, staleness orchestration, notifications, and operational Q&A.
- `rfi` owns canonical RFI numbering, evidence-backed drafting, validation, duplicate indicators, review/revisions, responses, impact records, reporting, audit, and operational Q&A.
- `submittal` owns cited requirement extraction/admission, register numbering, immutable packages and attachment revisions, attachment content evidence, proposed compliance mappings, completeness matrices, reviews, official dispositions, resubmittals, procurement planning, staleness, reporting, audit, and operational Q&A.
- `agents` defines narrow assistant behavior and a registry. An agent depends on interfaces, not concrete providers.
- `tools` defines explicitly bounded capabilities. Side-effecting tools will require authorization and audit records.
- `workflows` coordinates deterministic, reviewable processes. It is preferred over agent autonomy for known construction processes.
- `storage` contains persistence protocols; SQLite, filesystem, object storage, or hosted databases will be adapters.
- `prompts` will hold reviewed, versioned prompt assets only when model-backed functionality begins.
- `config` maps runtime environment into validated immutable settings.

## Dependency rules

1. Delivery and infrastructure code may depend on domain contracts; domain contracts do not import FastAPI, databases, or model SDKs.
2. Cross-module calls use protocols and typed request/response objects.
3. Constructor injection is the default. The container resolves dependencies only at application boundaries.
4. Model providers implement future interfaces and are selected in configuration. Provider-specific response objects never cross into domain modules.
5. Factual outputs carry citations. Inference and recommendation models must expose evidence and human-review status.

## Adding an agent

Implement the `agents.Agent` protocol in the capability module that owns the behavior. Inject retrieval, tools, and storage interfaces through its constructor. Register it with `AgentRegistry` during composition. Existing agents and the registry require no source changes. Add contract tests, grounded-output evaluations, and documented authorization boundaries before enabling it.

## FastAPI readiness

A future FastAPI adapter should create `Application` during lifespan startup, expose dependencies through thin route functions, validate requests with Pydantic, and delegate to workflows. HTTP concerns must not leak into workflows or domain models.

## Model readiness

Model interfaces are introduced only when a concrete use case defines their requirements. Cited Q&A has a provider-neutral grounded-answer contract, and Revision Intelligence has an optional summary protocol limited to validated deterministic findings. Local or OpenAI-compatible adapters must include timeouts, cancellation, token/cost controls, structured outputs, redaction, observability, and evaluations. Provider credentials stay in environment or secret storage and are never committed.

## Safety and trust

Source access must honor project permissions. Ingested content is untrusted input. Future implementations must address prompt injection, document malware, sensitive data, retention, auditability, stale versions, conflicting sources, and external side effects. Human review is an architectural state, not merely interface copy.

## Module placeholders

- Document Intelligence: ingestion, classification, metadata, parsing, version lineage
- Construction QA: cited questions across authorized project records
- Drawing Intelligence: sheet structure, details, callouts, revisions, cross-references
- Schedule Intelligence: activity mapping, look-aheads, constraints, variance
- Administrative Automation: RFIs, submittals, minutes, logs, follow-up
- Risk Detection: evidence-backed signals, confidence, disposition, feedback
- Project Memory: source-aware retrieval and longitudinal project knowledge
- Procurement: submittal-to-fabrication-to-delivery tracking
- Safety: documentation assistance without replacing competent-person authority
- Commissioning: readiness, testing evidence, issues, and turnover

## Document-ingestion pipeline

The first implemented capability follows a framework- and model-independent pipeline:

```text
File -> LocalFileLoader -> PageExtractor -> ConservativeMetadataExtractor
     -> DocumentPage records -> DeterministicTextChunker
     -> JsonDocumentRepository -> future retrieval adapters
```

Each stage has a typed interface. The service composes the stages without depending on OpenAI, local inference, a vector database, or FastAPI. Source bytes are hashed before extraction. Document and chunk identities derive from stable source inputs, and chunks never span pages. Each chunk owns a `CitationReference` containing the source document name, page, optional sheet/specification metadata, chunk ID, and source location.

The local JSON repository is an adapter, not a domain dependency. PostgreSQL, object storage, or vector indexing can be added later without changing extraction or chunking. See [`document-ingestion.md`](document-ingestion.md).

## Retrieval and cited-answer flow

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

`LocalProjectRetriever` reads validated ingestion aggregates through the repository interface and filters by project before scoring. `EvidenceAssessor` describes sufficiency and flags materially relevant measurement or approval-state conflicts. `CitedQuestionAnsweringService` supplies retrieved evidence to a provider, rejects unknown citation IDs and fabricated quotations, rebuilds citations from source chunks, and fails closed when provider output is invalid.

Retrieval and answer generation are separate protocols. A future BM25, vector, hybrid, metadata, or reranking implementation can replace retrieval without changing answer providers. The default extractive provider needs no model. The optional OpenAI-compatible adapter is configured only at the delivery layer and returns a validated `AnswerDraft`; provider response objects never enter the domain model.

## Revision Intelligence flow

```text
Old revision + New revision
  -> lineage validation -> comparability -> source-mapped normalization
  -> deterministic alignment -> token diff -> construction classification
  -> significance and review state -> citation validation
  -> JSON persistence -> Markdown/JSON report -> cited QA
```

Comparison services depend on repository protocols. Exact source excerpts remain separate from normalized matching text. External analysis cannot replace deterministic findings or source citations.

Revision comparison remains independent from operational review. `ProjectChangeService` consumes saved comparison models through an application boundary; Revision Intelligence does not import the workflow package. `app.api` and `app.change_cli` are thin adapters over canonical services. The legacy `src/ai_project_engineer` application is an isolated deprecated compatibility path under [ADR 0002](decisions/0002-isolate-legacy-project-engineer.md).

## RFI workflow boundary

```text
Revision finding -> ProjectChange -> deterministic RFI draft + source citations
                                      -> quality/duplicate assessment
                                      -> internal review + immutable revisions
                                      -> explicit issue + official response
                                      -> conservative impact analysis
                                      -> human project-change resolution + RFI closure
```

`rfi` uses the existing project-change repository only at an application-service integration boundary for bidirectional links, dispositions, closure checks, and the local notification outbox. It does not mutate Revision Intelligence. The generic legacy RFI related item is retained only as a traceable compatibility pointer; `rfi.RFI` is canonical. HTTP and CLI adapters remain thin, and provider failures retain deterministic output. See [`rfi-automation.md`](rfi-automation.md).

## Submittal workflow boundary

```text
Ingested specification -> deterministic cited candidates -> human admission
  -> project register -> immutable package revision -> completeness matrix
  -> internal approval -> explicit issue -> official design-team disposition
  -> resubmittal/staleness review -> human procurement release/closure
```

The `submittal` module reads document aggregates through a repository adapter and integrates with project changes, RFIs, and the local notification outbox at service boundaries. Completeness is content-presence validation, never technical compliance. Informal responses, official responses, and Brunel analysis are separate types and states. Schedule links are references only, and procurement release is always human-controlled. Generic `WorkflowType.SUBMITTAL` related items remain compatibility pointers; canonical lifecycle data lives in `submittal`. See [`submittal-automation.md`](submittal-automation.md).

## Submittal attachment intelligence boundary

```text
Local attachment -> security/hash/immutable revision -> canonical document ingestion
  -> readability + deterministic classification/extraction + exact chunk citations
  -> package evidence set -> missing/mismatch/conflict/deviation indicators
  -> proposed requirement mappings -> explicit human confirmation
  -> package staleness + revision comparison + cited search/Q&A/export
```

Attachment binaries are owned by a replaceable `AttachmentFileStore`; local JSON stores only domain metadata, lineage, extraction results, evidence sets, reviews, comparisons, and audit references. Supported content is not parsed through a competing pipeline: PDF, TXT, and Markdown reuse `DocumentIngestionService` and `JsonDocumentRepository`. Unsupported allowed formats remain metadata-only unresolved evidence and cannot satisfy a mapping.

Evidence sets are immutable snapshots keyed by attachment hashes, extraction identities, requirement identities, and versioned policies. Proposed mappings distinguish specification citations from submitted-attachment citations and stay `unreviewed`, `confirmed`, `modified`, `rejected`, or `needs_information`. Later evidence changes preserve prior official dispositions while invalidating internal review currency when applicable. See [`submittal-attachment-intelligence.md`](submittal-attachment-intelligence.md).

