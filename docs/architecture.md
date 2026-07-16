# Architecture

## Approach

Construction Copilot uses a modular monolith initially. Each capability owns a coherent contract and can evolve internally without forcing distributed-system complexity. Modules communicate through typed interfaces and Pydantic boundary models. Infrastructure and frameworks depend inward on these contracts.

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

No model interface is implemented until a real use case defines its requirements. When needed, create a provider-neutral protocol and adapters for local inference and OpenAI. Include timeouts, cancellation, token/cost controls, structured outputs, redaction, observability, and evaluations. Provider credentials stay in environment or secret storage and are never committed.

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

