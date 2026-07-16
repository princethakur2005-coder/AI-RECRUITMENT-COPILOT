# AI Recruitment Copilot

Comprehensive project documentation, developer guide, architecture overview, and release preparation notes for the AI Recruitment Copilot platform.

---

## Table of Contents

- **Project**
	- [Project Overview](#project-overview)
	- [Feature Matrix](#feature-matrix)
	- [Technology Stack](#technology-stack)
	- [Directory Structure](#directory-structure)
- **Architecture**
	- [High-level Architecture](#high-level-architecture)
	- [Data Flow & Components](#data-flow--components)
- **Getting Started**
	- [Installation](#installation)
	- [Local Development](#local-development)
	- [Environment Configuration](#environment-configuration)
	- [Deployment Guide](#deployment-guide)
- **Developer Guide**
	- [Developer Setup](#developer-setup)
	- [Coding Conventions](#coding-conventions)
	- [Project Structure Explanation](#project-structure-explanation)
	- [Contribution Guide](#contribution-guide)
	- [Development Workflow](#development-workflow)
- **API**
	- [API Overview](#api-overview)
	- [Authentication Overview](#authentication-overview)
	- [Endpoint Organization](#endpoint-organization)
	- [Error Response Conventions](#error-response-conventions)
- **Operations & Release**
	- [CHANGELOG & Release Notes Template](#changelog--release-notes-template)
	- [Version Metadata](#version-metadata)
	- [Release Checklist](#release-checklist)
	- [Production Readiness Checklist](#production-readiness-checklist)
- **Support**
	- [Troubleshooting Guide](#troubleshooting-guide)
	- [FAQ](#faq)
	- [Security Notes](#security-notes)

---

## Project Overview

AI Recruitment Copilot is an extensible platform that provides candidate and job management, interview workflows, and AI-assisted recruitment intelligence. It is built as a modular FastAPI backend with a React/TypeScript frontend.

Goals:
- Provide robust APIs for recruiting workflows
- Offer modular engines for resume intelligence, interview automation, and evaluation
- Ship production-ready security, testing, and deployment patterns

## Feature Matrix

- Candidate management: create, update, search, track
- Job management: post, update, publish, analytics
- Resume intelligence: parsing, scoring, recommendations
- Interview engine: scheduling, question generation
- Evaluation engine: automated prompt evaluations, audit logs
- Authentication & RBAC: JWT-based auth and role checks
- Observability: metrics, health checks, request tracing

## Technology Stack

- Backend: Python 3.11+ (FastAPI, SQLAlchemy, Alembic)
- Frontend: React + TypeScript
- Database: PostgreSQL (production), SQLite used for tests
- Cache: Redis (optional)
- Auth: JWT (PyJWT)
- Testing: Pytest, Playwright (E2E), Jest + Testing Library (frontend)
- CI/CD: Declarative pipelines (CI must run tests, lint, build images, and deploy)

## Directory Structure

Top-level overview (abridged):

- `backend/` — FastAPI app
	- `app/` — application code (api, core, db, models, middleware, services)
	- `tests/` — unit and integration tests
- `frontend/` — React application
- `ai/` — AI engines (resume, interview, evaluation)
- `infrastructure/` — containerization and deployment pieces

See [structure.txt](structure.txt) for a full directory listing.

## High-level Architecture

The system uses a service-oriented design:

- FastAPI backend exposes REST endpoints and internal services.
- Frontend calls backend APIs and hosts the SPA.
- Redis is used for caching and lightweight queues.
- PostgreSQL is the primary relational store.
- Background workers (optional) process async jobs.

Components:
- API layer: request validation, authentication, routing
- Services: business logic, cache, job queue placeholders
- Middleware: security, request logging, rate limiting, resilience
- AI engines: separate modules invoked by services

## Data Flow & Components

1. Client calls frontend UI
2. Frontend uses JWT to call backend endpoints
3. Backend routes to service layers
4. Services interact with DB/Redis and call AI engines as needed
5. Middleware captures request id, metrics, security headers, and error handling

## Installation

Prerequisites:
- Python 3.11+ (recommended: use the project venv)
- Node 18+ (for frontend)
- PostgreSQL for production
- Redis for caching (optional)

Backend quick start (local dev):

1. Create virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

2. Configure environment variables (see Environment Configuration below).
3. Run migrations (alembic) and start the app with Uvicorn.

## Local Development

- Backend: run with `uvicorn app.main:app --reload --port 8000` from `backend/`
- Frontend: `cd frontend && npm install && npm run dev`
- Use `.env` files in dev to set `DATABASE_URL`, `SECRET_KEY`, etc. See `backend/app/core/config.py` for names.

## Environment Configuration

Key environment variables (non-exhaustive):
- `DATABASE_URL` — Postgres connection string
- `SECRET_KEY` — application secret for JWT signing
- `REDIS_URL` — Redis connection string
- `DEBUG` — boolean to enable debug mode
- `ALLOWED_HOSTS`, `CORS_ORIGINS` — security lists

The backend loads env from `backend/.env` by default. Ensure secrets are managed securely in production.

## Deployment Guide

This project is container-ready. Typical deployment steps:

1. Build backend image (Dockerfile in `backend/`)
2. Build frontend static assets and serve via CDN or with nginx
3. Provision Postgres & Redis in target environment
4. Run database migrations
5. Start backend with a process manager (Gunicorn+Uvicorn workers) behind a reverse proxy (nginx)
6. Configure HTTPS and HSTS

See `infrastructure/docker/` and `infrastructure/kubernetes/` for deployment assets.

## Troubleshooting Guide

- Backend fails to start: check `DATABASE_URL`, migrations, and `SECRET_KEY`.
- 500 errors in production: check logs, correlation/request id header, and metrics endpoint.
- Slow queries: enable query logging and inspect DB indexes.

## FAQ

- Q: Where are environment variables defined?
	- A: In `backend/.env` for local development; production uses secrets management.
- Q: How do I run tests?
	- A: Backend: `pytest -q` in `backend/`. Frontend: `npm test` in `frontend/`.

## Security Notes

- JWT tokens are validated with audience/issuer checks.
- HSTS, CSP, secure cookies, and other HTTP security headers are enforced in middleware.
- Rotate `SECRET_KEY` carefully; old tokens will be invalidated.

---

## Developer Documentation

### Developer Setup

1. Clone repository
2. Create Python virtualenv and install backend deps
3. Install Node modules for frontend
4. Configure `backend/.env` and local Postgres
5. Run migrations and start services locally

### Coding Conventions

- Python: follow PEP8 and use black/isort for formatting
- Types: prefer type hints; use Pydantic models for API schemas
- JS/TS: follow project ESLint/Prettier configuration

### Project Structure Explanation

- `backend/app` — core API implementation. Key packages:
	- `api/` — route handlers
	- `core/` — configuration, security, logging, exceptions
	- `db/` — database engine and session
	- `middleware/` — middlewares for request handling
	- `services/` — reusable services (cache, background job placeholders)

### Contribution Guide

- Fork the repo, create a feature branch, implement changes with tests, and open a pull request.
- Follow commit message conventions and include descriptive PR summaries.

### Development Workflow

- Use feature branches and PR reviews
- CI runs linting, tests, and builds. Address pipeline errors before merging.

---

## API Documentation

### API Overview

The backend exposes RESTful endpoints under `/api/*` with JSON payloads. Use OpenAPI docs served at `/docs` in development.

### Authentication Overview

- JWT-based authentication. Obtain access token via auth endpoints and send `Authorization: Bearer <token>` on requests.
- Some internal test helpers expose a token endpoint for E2E/local automation (check tests/helpers).

### Endpoint Organization

- `app/api/` contains grouped routers by domain: `auth`, `user`, `job`, `candidate`, `note`, `offer`, `search`, `workspace`, etc.

### Error Response Conventions

All API errors return a unified JSON structure:

```json
{
	"code": "error_code",
	"message": "User-safe message",
	"request_id": "uuid-or-none",
	"details": null
}
```

- `code`: machine-friendly error code
- `message`: short human-friendly message
- `request_id`: correlation id for tracing
- `details`: environment-aware debug details (only in DEBUG or verbose mode)

---

## Release Preparation

### CHANGELOG (template)

Maintain `CHANGELOG.md` with semantic headings. Example entry:

```
## [Unreleased]

### Added
- Feature: Description (PR #123)

### Fixed
- Bugfix: Description (PR #124)

### Security
- Hardened JWT validation (ISS/AUD checks)
```

### Release Notes Template

- Version: `vX.Y.Z`
- Date: YYYY-MM-DD
- Summary: short summary of release
- Highlights:
	- Feature A
	- Fix B
- Breaking changes: list if any
- Upgrade notes: DB migrations, env changes

### Version Metadata

Store version metadata in a central place (tagged git releases and changelog). Use semver.

### Release Checklist

1. Run full test suite (unit, integration, E2E)
2. Ensure CI pipelines green
3. Build artifacts and verify image scanning
4. Run migration plan in a staging environment
5. Update `CHANGELOG.md`
6. Tag release and push artifacts

### Production Readiness Checklist

- Secrets: ensure `SECRET_KEY`, DB creds, and third-party API keys are in secrets manager
- Observability: metrics endpoint, logs shipped to central system, alerting rules
- Backups: DB backups configured and tested
- Scaling: connection pool and autoscaling validated
- Security: vulnerability scan and dependency updates

---

## Troubleshooting

- Inspect logs and correlate with `request_id` header present on all responses.
- Use health endpoints `/health`, `/health/ready`, `/health/live` to diagnose dependency issues.

## FAQ

- Q: How to add a new API route?
	- A: Add router in `app/api/<domain>.py`, register in `app/main.py`, add tests and docs.

## Security Notes

- Keep `DEBUG` off in production. Ensure `SECRET_KEY` is not the default.
- CSP, HSTS, secure cookies, and CSRF options are configurable in `backend/app/core/config.py`.

---

For contributor, developer and release checklists please see the relevant sections above.

If you'd like separate CHANGELOG or CONTRIBUTING files created, run the documented templates in this README or request creation.

