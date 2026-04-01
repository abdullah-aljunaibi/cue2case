# Cue2Case

Cue2Case is an explainable port-approach anomaly triage and case-building system built as a strong prototype for turning vessel behavior into reviewable cases.

## Why this project exists

Most anomaly pipelines stop at alerts. That is useful for scoring, but weak for review. Operators still need to answer basic questions fast: what happened, why did the system flag it, what evidence supports the call, and what should be looked at next.

Cue2Case was built around that gap. The goal is to take AIS-derived anomalies and turn them into cases that a human can inspect, compare, and explain.

## What makes it different

The core idea is case-first workflow, not detector-first workflow.

Instead of asking a reviewer to dig through raw alerts, Cue2Case groups signals into cases with explicit reasons, supporting evidence, and map context. That matters for demos, interviews, and applied review because the system can show not just that something was flagged, but why it was flagged and what the reviewer should inspect.

## System overview

Cue2Case has a straightforward pipeline:

1. AIS ingestion
2. Track segmentation
3. Detector pass
4. Case engine
5. API
6. Web UI

Current detector set:

- abnormal_approach
- ais_silence
- loitering
- kinematic_anomaly
- identity_anomaly

The result is a case-oriented workflow over AIS activity near port approaches, with explanations attached to the output instead of left implicit inside model logic.

## Current product surfaces

The current prototype exposes four main surfaces:

- queue: list of generated cases for review
- case detail: per-case explanation and evidence view
- map staging: geographic context for cases
- external cues: supporting cue layer used in the demo

These surfaces are enough to show the end-to-end flow from detection to case review, but they should be read as prototype-grade product surfaces, not finished operational tooling.

## Verified demo metrics

These numbers are from the current demo dataset and evaluation outputs:

- 333 vessels
- 132,942 AIS positions
- 614 track segments
- 4,470 alerts
- 656 cases
- 3 external cues
- suspicious reasons coverage: 82.8%
- benign reasons coverage: 92.2%
- explanations present: 100%
- geofence context present: 93.5%

## Tech stack

- FastAPI for the API layer
- PostgreSQL + PostGIS for storage and spatial queries
- Next.js for the web UI
- Docker Compose for local setup

## Quick start

The repo is set up to run locally with Docker Compose.

1. Make sure Docker and Docker Compose are available.
2. The repo already includes a `.env`. If you need custom settings, copy or edit it before startup.
3. Start the stack:

```bash
docker compose up --build
```

Once the services are up:

- web UI: http://localhost:3000
- API: http://localhost:8000
- API health endpoint: http://localhost:8000/health

Default local assumptions from `docker-compose.yml`:

- Postgres runs on localhost:5433
- API runs on localhost:8000
- Web runs on localhost:3000

## Smoke check

A basic smoke test is included to verify the main API paths and the current case-detail contract.

Run it after the stack is up:

```bash
./scripts/smoke-check.sh
```

It checks:

- `/health`
- `/cases?limit=1`
- `/cases/{uuid}`
- `/map/cases?limit=1`

Recent credibility fixes already shipped in the repo include:

- `evaluate.py` host/container DB resolution fix
- UUID case-detail API contract fix
- explicit `confidence_score` migration
- `scripts/smoke-check.sh`

## Repository structure

```text
api/                  FastAPI application
db/init/              database initialization and seed setup
docs/                 supporting project docs
scripts/smoke-check.sh basic API smoke test
web/                  Next.js frontend
docker-compose.yml    local multi-service runtime
```

## What is production-ready vs prototype-grade

What is solid now:

- end-to-end local startup with Docker Compose
- explainable case flow from AIS-derived signals to reviewable cases
- API and UI surfaces that support a working demo
- shipped fixes around DB resolution, UUID case detail, and confidence score handling

What is still prototype-grade:

- the project should be treated as an application artifact, not an operational deployment
- detector output, cue usage, and map workflows are demo-ready but not production-hardened
- there is no claim here of full reliability, scale testing, security hardening, or operational readiness

Short version: this is a strong prototype with a clear product idea, not a production system.

## Next improvements

The obvious next steps are practical ones:

- tighten evaluation and reporting around case quality
- improve case review workflow depth in the UI
- harden the detector-to-case pipeline for less demo-specific operation
- expand validation around external cue handling and map context
- add more operational checks beyond the current smoke test

## Demo and docs

- See `docs/` for supporting material.
- Run the local stack and use the web UI at `http://localhost:3000` for the demo path.
- Use the API at `http://localhost:8000` for direct inspection and smoke testing.
