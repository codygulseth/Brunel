# Construction Copilot

> An AI operating system for commercial construction—not a chatbot.

Construction Copilot exists to **automate administrative work, instantly retrieve project knowledge with citations, proactively identify risks, and help construction teams make better decisions.** It is designed for Project Engineers, Project Managers, Superintendents, and Owners.

This repository is currently at the **project-foundation stage**. It defines maintainable package boundaries and typed interfaces. It does not yet ingest documents, call an AI model, make recommendations, or automate construction processes.

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
tools/                 Safe capability contracts
workflows/             Deterministic process orchestration contracts
models/                Shared domain value objects
prompts/               Versioned prompt contracts
storage/               Persistence interfaces
config/                Typed settings and environment examples
tests/                 Unit, contract, and legacy prototype tests
docs/                  Vision, roadmap, and architecture
```

The earlier Project Organization and Responsibility Registry remains available under `src/ai_project_engineer/` as a working prototype. Future feature migration should happen deliberately, module by module.

## Local setup (Windows PowerShell)

Requires Python 3.12 or newer.

```powershell
cd "C:\Users\14027\OneDrive\Documents\AI Project Engineer"
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

Settings use `CC_*` environment variables. See `config/example.env`. Model access defaults to `disabled`; no credentials or external services are required.

## Developer workflow

Keep domain modules independent. Depend on protocols in neighboring packages, inject adapters at `app/bootstrap.py`, add Pydantic models at boundaries, and include tests with every implementation. Architecture decisions that change a boundary should be recorded under `docs/decisions/`.

See [vision](docs/vision.md), [roadmap](docs/roadmap.md), and [architecture](docs/architecture.md).
