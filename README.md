# AI Project Engineer

An early, local-only prototype for commercial-construction project organization and responsibility tracking. Lesson 1 provides a fictional data-center project registry, server-rendered web pages, and a JSON API. It does **not** make contractual, engineering, safety, or approval decisions.

## Windows PowerShell setup

Open PowerShell in the parent folder, then copy and paste:

```powershell
cd "C:\Users\14027\OneDrive\Documents\AI Project Engineer"
code .
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
python -m ai_project_engineer.seed
python -m uvicorn ai_project_engineer.main:app --reload
```

Open <http://127.0.0.1:8000> in a browser. In a second PowerShell window, activate the environment and run tests:

```powershell
cd "C:\Users\14027\OneDrive\Documents\AI Project Engineer"
.\.venv\Scripts\Activate.ps1
python -m pytest
deactivate
```

The editable install makes the `src` package importable while keeping your local code changes immediately available.

## Seed data

`python -m ai_project_engineer.seed` loads `sample_data/lesson_01/fictional_data_center_project.json`. It is safe to run repeatedly; the project number prevents duplicates.

## Troubleshooting

- **Activation is blocked:** run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then activate again. This changes policy only for the current PowerShell session.
- **`python` is not recognized:** install Python 3.12+ from python.org, select “Add Python to PATH,” reopen PowerShell, and try `py -3.12` in place of `python` if the launcher is available.
- **Port 8000 is in use:** start with `python -m uvicorn ai_project_engineer.main:app --reload --port 8001`, then open <http://127.0.0.1:8001>.
- **Reset SQLite:** stop the server, run `Remove-Item .\ai_project_engineer.db`, then `python -m ai_project_engineer.seed`. This intentionally removes local development data.

## API

Interactive API documentation is available at <http://127.0.0.1:8000/docs>. POST endpoints accept JSON for organizations, people, and responsibilities.
