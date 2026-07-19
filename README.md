# Brunel

Brunel now includes Meeting Minutes and Action Tracking: immutable meeting records, cited deterministic proposals, human-confirmed action and decision registers, carry-forward, minutes review, comparisons, dashboards, and operational Q&A.

Brunel includes a conservative Drawing Intelligence foundation for immutable PDF drawing-set revisions, sheet/index identification, explicit reference graphs, visual-region citations, controlled OCR, validation, search, and text-level comparison. See [Drawing Intelligence Foundation](docs/drawing-intelligence-foundation.md).

> An elite AI construction copilot—not a chatbot.

Brunel is **an elite AI construction copilot that serves as an intelligent assistant to Project Engineers, Project Managers, Superintendents, and Owners by automating administrative work, understanding project documentation, providing evidence-backed answers, and proactively identifying project risks.**

This repository includes Brunel's project foundation, deterministic document ingestion, cited project question answering, Revision Intelligence, operational project-change review, evidence-backed RFI automation, submittal automation, and cited submittal attachment intelligence. It does not yet provide OCR, drawing vision, production vector retrieval, external document-control integration, or automated construction decisions.

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
submittal/             Requirements, packages, attachment evidence, reviews, responses, procurement
procurement/           Register, lead times, date plans, release guardrails, exposure, delivery
schedule_intelligence/ Immutable revisions, quality, CPM evidence, lineage, schedule comparison
field_intelligence/    Daily reports, reviewed field records, progress proposals, field dashboards
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

## Submittal automation

Brunel can extract cited submittal requirements from project specifications, route human admission decisions into a project-scoped register, assemble immutable package revisions, block incomplete packages, require internal approval before issue, record official design-team dispositions separately from internal notes and Brunel inference, manage revise-and-resubmit history, calculate deterministic procurement planning dates, and require human procurement release.

Brunel now has a canonical Procurement Intelligence foundation: cited candidate review, project-scoped numbering and registers, source-preserving lead-time history, transparent calendar-day plans, dependencies and milestones, human-only release authorization, versioned forecasts, explainable exposure, delivery/acceptance separation, staleness, dashboards, and plan comparison. It never places orders, commits funds, approves vendors/products, or edits the schedule. See [Procurement Intelligence](docs/procurement-intelligence.md).

The module also provides audit history, local notifications, logs, dashboards, Markdown/JSON/CSV output, FastAPI routes, CLI commands, RFI/project-change links, staleness handling, and cited operational Q&A. It does not determine technical compliance or contact external systems. See [Submittal automation](docs/submittal-automation.md).

## Submittal attachment intelligence

Brunel can register immutable attachment revisions, route supported PDF/TXT/Markdown content through canonical ingestion, assess readability, classify submitted document types, extract cited product identities and technical attributes, flag duplicate/missing/mismatched/conflicting evidence, and generate deterministic proposed requirement mappings. Every proposal remains a human-review state; it never becomes an official disposition or professional design-compliance finding automatically.

```powershell
python -m app.cli submittal-attachment-add --project-id demo-project --package-id package-id --file .\product-data.pdf --declared-type product_data
python -m app.cli submittal-attachment-analyze --project-id demo-project --package-id package-id
python -m app.cli submittal-attachment-ask --project-id demo-project --package-id package-id --question "What model and short-circuit rating were submitted?"
python -m app.cli submittal-attachment-demo --project-id synthetic-attachment-demo
```

The synthetic demo creates only generated switchboard text under the ignored data directory and performs no model calls, external notifications, uploads, procurement actions, schedule changes, or approvals. See [Submittal Attachment Intelligence](docs/submittal-attachment-intelligence.md).
