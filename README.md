# Brunel

> An elite AI construction copilot—not a chatbot.

Brunel is **an elite AI construction copilot that serves as an intelligent assistant to Project Engineers, Project Managers, Superintendents, and Owners by automating administrative work, understanding project documentation, providing evidence-backed answers, and proactively identifying project risks.**

This repository includes Brunel's project foundation, deterministic document ingestion, cited project question answering, Revision Intelligence, operational project-change review, and evidence-backed RFI automation. It does not yet provide OCR, drawing vision, production vector retrieval, external document-control integration, or automated construction decisions.

## Product principles

- Project evidence comes before generated answers; factual output must be traceable through citations.
- The system supports construction professionals and does not replace contractual authority, licensed design judgment, safety responsibility, or human approval.
- Deterministic workflows are preferred where AI is unnecessary.
- External actions require clear authorization and human review.
- Model providers are adapters. Core modules remain usable with local models, OpenAI models, or no model.
- New agents and construction capabilities are added through stable interfaces, not edits to a central decision engine.

## Foundation layout

```text
app/                  Application composition and future delivery adapters
core/                 Dependency injection and logging
agents/               Agent contracts and registry
document_processing/  Document intake and parsing contracts
rag/                   Citation-aware retrieval contracts
revision_intelligence/ Revision lineage, alignment, diffing, classification, reports
change_workflow/       Assignable, auditable project change review and resolution
rfi/                   Evidence-backed RFI drafting, review, response, logs, and audit
tools/                 Safe capability contracts
workflows/             Deterministic process orchestration contracts
models/                Shared domain value objects
prompts/               Versioned prompt contracts
storage/               Persistence interfaces
config/                Typed settings and environment examples
tests/                 Unit, contract, and legacy prototype tests
docs/                  Vision, roadmap, and architecture
```

The earlier `src/ai_project_engineer` prototype is isolated as deprecated compatibility code under ADR 0002. Canonical capabilities live in the top-level modules and do not import it.

## Local setup (Windows PowerShell)

Requires Python 3.12 or newer.

```powershell
Set-Location <path-to-your-Brunel-repository>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -m pytest
```

To run the existing registry prototype:

```powershell
python -m ai_project_engineer.seed
python -m uvicorn ai_project_engineer.main:app --reload
```

Open <http://127.0.0.1:8000>. API documentation is at <http://127.0.0.1:8000/docs>.

## Configuration

Settings use `BRUNEL_*` environment variables. See `config/example.env`. Model access defaults to `disabled`; no credentials or external services are required.

## Developer workflow

Keep domain modules independent. Depend on protocols in neighboring packages, inject adapters at `app/bootstrap.py`, add Pydantic models at boundaries, and include tests with every implementation. Architecture decisions that change a boundary should be recorded under `docs/decisions/`.

See [vision](docs/vision.md), [roadmap](docs/roadmap.md), and [architecture](docs/architecture.md).

## Document ingestion

Brunel currently ingests PDF, UTF-8 TXT, and Markdown files. It validates and hashes the source, extracts page records, retains explicitly provided construction metadata, creates deterministic page-bound chunks, embeds a citation reference in each chunk, and stores the aggregate as local JSON.

```powershell
python -m app.cli ingest --project-id demo-project --file .\path\to\document.pdf
```

Optional metadata includes `--document-type`, `--title`, `--revision`, `--revision-date`, `--sheet-number`, and `--specification-section`. Generated records are written under `data/ingested/` by default and are ignored by Git. Set `BRUNEL_DATA_DIRECTORY` to choose another local data root.

The current pipeline does not perform OCR. Image-only PDF pages are retained as empty page records with warnings so source page numbering is never lost. Drawing geometry, title-block interpretation, spreadsheets, schedules, and semantic retrieval are intentionally deferred. See [document ingestion](docs/document-ingestion.md) for the full design and limitations.

## Search and cited questions

Search a project's ingested chunks without generating an answer:

```powershell
python -m app.cli search --project-id demo-project --query "generator pad concrete strength" --top-k 5
```

Ask Brunel for an evidence-backed answer:

```powershell
python -m app.cli ask --project-id demo-project --question "What concrete strength is required for the generator pad?"
```

Retrieval is project-scoped and deterministic. It combines normalized term coverage, term frequency, exact phrases, and construction identifiers such as sheet, room, RFI, submittal, revision, and specification references. Every factual answer includes citations built from the retrieved source chunks. If evidence is absent, partial, or conflicting, Brunel says so rather than guessing.

The default `extractive` answer provider runs locally and quotes source text directly. An OpenAI-compatible provider can be explicitly configured through environment variables; it is disabled unless selected and validates structured output with bounded retries. See [retrieval and cited QA](docs/retrieval-and-cited-qa.md) and [configuration](docs/configuration.md).

## Revision Intelligence

Register related documents with `--document-family-id`, `--revision-sequence`, and optionally `--supersedes-document-id`, then compare them locally:

```powershell
python -m app.cli compare --project-id demo-project --old-document-id doc_old --new-document-id doc_new --output reports/change-report.md
python -m app.cli comparison-list --project-id demo-project
python -m app.cli ask --project-id demo-project --question "What changed in the switchgear lead time?"
```

The pipeline preserves exact old/new excerpts and page/chunk citations, flags construction-significant changes, and labels implications as requiring human review. See [Revision Intelligence](docs/revision-intelligence.md).

## Revision review workflow

Material revision findings can enter an idempotent project change register, receive assignments and due dates, move through validated review states, retain dispositions and append-only notes, create minimal linked draft actions, and remain traceable through audit history to original evidence. A project dashboard prioritizes open, overdue, high-priority, and stale-source changes. See [revision review workflow](docs/revision-review-workflow.md) and the [development API](docs/api.md).

## RFI automation

Project changes can now generate canonical, project-scoped RFI drafts that preserve their original citations. Brunel provides deterministic drafting and quality checks, duplicate indicators, sequential numbering, internal review and immutable text revisions, explicit official responses, conservative response analysis, human-confirmed impact records, logs, dashboards, audit history, a local notification outbox, FastAPI routes, CLI workflows, and operational RFI Q&A.

RFIs are internal records only. Drafts require human approval, official responses must be explicitly identified, and Brunel never confirms cost or schedule impact automatically. No email or external document-control action occurs. See [RFI automation](docs/rfi-automation.md).
