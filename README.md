# CodeDNA

**AI-Powered Code Intelligence & Change Impact Analysis Platform**

CodeDNA is a developer tool designed to analyze source code,
map dependencies, identify potentially impacted components,
and support safer code changes.

## Project Status

Phase 1 — Backend Foundation

Implemented:
- Modular FastAPI backend
- Versioned REST API
- Pydantic response validation
- Interactive Swagger documentation
- Automated API tests with Pytest
- Code linting with Ruff

## Planned Features

- Repository scanning
- Static code analysis
- Dependency graph generation
- Git diff analysis
- Change impact detection
- Explainable risk scoring
- Test recommendations
- AI-powered explanations
- GitHub Pull Request integration
- Interactive React dashboard

## Tech Stack

Currently implemented:
- Python
- FastAPI
- Pydantic
- Pytest
- Ruff

Planned:
- PostgreSQL
- SQLAlchemy
- Python AST and Tree-sitter
- NetworkX
- React and TypeScript
- Cytoscape.js
- Docker

## Local Setup

```bash
git clone <repository-url>
cd CodeDNA/backend

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -e ".[dev]"
```

## Run Backend

```bash
python -m uvicorn app.main:app --reload --port 8001
```

API Documentation:
http://127.0.0.1:8001/docs

Health Endpoint:
http://127.0.0.1:8001/api/v1/health

## Run Tests

```bash
python -m pytest -v
python -m ruff check app tests
```

## Architecture

- `backend/app/api` — HTTP API routes
- `backend/app/core` — Application configuration
- `backend/app/schemas` — Pydantic data schemas
- `backend/tests` — Automated tests
- `frontend` — React application (planned)

## Development Roadmap

CodeDNA is being developed incrementally.
Each feature will be implemented and tested before
being marked as complete.
