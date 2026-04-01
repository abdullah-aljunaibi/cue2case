# submission package

## 1. Submission summary blurb

Cue2Case is an explainable port-approach anomaly triage and case-building system built by Abdullah Al Junaibi. It takes AIS-derived vessel activity and turns it into reviewable cases rather than leaving an analyst to sort through raw alerts. The current stack uses FastAPI, PostgreSQL/PostGIS, Next.js, and Docker Compose.

The problem it addresses is simple: anomaly detection on its own is not enough for review. An operator still needs to know what happened, why it was flagged, what evidence supports it, and what to inspect next. Cue2Case is designed around that review step. Its pipeline runs from AIS ingestion to segmentation, through detector output, into a case engine, then exposes the results through an API and a web UI.

What makes the prototype different is the workflow. Cue2Case is case-first, not map-first. Instead of asking a reviewer to hunt through alerts and then reconstruct the story, it groups signals into cases with explicit explanations, evidence, and map context. The current product surfaces cover the core review path: queue, case detail, map staging, and external cues.

As a prototype, it proves that the end-to-end path works on a real demo dataset: 333 vessels, 132,942 AIS positions, 614 track segments, 4,470 alerts, and 656 generated cases, with 3 external cues in the current demo. It also shows strong explainability coverage in the current outputs: 82.8% suspicious reasons, 92.2% benign reasons, 100% explanations, and 93.5% geofence context. This should be read as application-ready prototype work, not a production deployment.

## 2. GitHub repo description + tagline

**Repo description:** Explainable port-approach anomaly triage and case-building prototype using FastAPI, PostgreSQL/PostGIS, Next.js, and Docker Compose. Turns AIS-derived detector output into reviewable cases with explanations, evidence, map context, and external cues.

**Tagline:** Case-first anomaly review for port approaches.

## 3. Drive handoff text

This package contains the Cue2Case source repo, supporting docs, and the screenshots used for review. The project runs locally with Docker Compose; from the repo root, start it with `docker compose up --build`. Once it is up, the web UI is available at `http://localhost:3000` and the API health check is at `http://localhost:8000/health`. If you want a quick verification pass first, run `./scripts/smoke-check.sh` after startup. I would start with the queue page, then open a high-score case detail view, then check the map and external cues pages. The evaluation report (`python api/app/evaluate.py`) gives the dataset and explainability metrics behind the demo. This is a strong prototype built to show workflow, explainability, and product thinking, not a production-hardened system.

## 4. Screenshots plan / capture checklist

1. **Queue page**
   - **View:** Main case queue
   - **URL:** `http://localhost:3000/`
   - **Show:** The list of generated cases, visible scores or priority cues, and enough rows to show this is a review queue rather than a single demo card.
   - **Suggested filename:** `01-queue-page.png`

2. **Case detail page (high-score case)**
   - **View:** Individual case detail for one of the top anomaly-score cases
   - **URL:** `http://localhost:3000/cases/<case-uuid>`
   - **Show:** Title, anomaly score, explanation, evidence, and any visible reasoning or context blocks. Use a UUID from the highest-scoring case surfaced by the API or evaluation output.
   - **Suggested filename:** `02-case-detail-high-score.png`

3. **Map staging view**
   - **View:** Map page
   - **URL:** `http://localhost:3000/map`
   - **Show:** Geographic case context, plotted cases or tracks, and enough of the map UI to make the spatial review workflow obvious.
   - **Suggested filename:** `03-map-staging.png`

4. **External cues page**
   - **View:** External cues surface
   - **URL:** `http://localhost:3000/external-cues`
   - **Show:** The external cue list or table, cue types, and any visible linkage between cues and case review.
   - **Suggested filename:** `04-external-cues.png`

5. **API health endpoint**
   - **View:** Browser tab showing API health response
   - **URL:** `http://localhost:8000/health`
   - **Show:** A successful health response from the running FastAPI service.
   - **Suggested filename:** `05-api-health.png`

6. **Smoke check terminal output**
   - **View:** Terminal after smoke test completes
   - **URL / command:** Run `./scripts/smoke-check.sh` from the repo root
   - **Show:** Successful checks for `/health`, `/cases?limit=1`, `/cases/{uuid}`, and `/map/cases?limit=1`.
   - **Suggested filename:** `06-smoke-check-terminal.png`

7. **Evaluation report terminal output**
   - **View:** Terminal with evaluation report
   - **URL / command:** Run `python api/app/evaluate.py` from the repo root
   - **Show:** Dataset summary counts, alert distribution, case distribution, top cases by anomaly score, cue coverage, explainability coverage, and geofence context coverage.
   - **Suggested filename:** `07-evaluation-report-terminal.png`

8. **Optional combined submission cover image**
   - **View:** A clean collage or contact-sheet style image assembled from the best four product screenshots
   - **URL:** Use the captures above
   - **Show:** Queue, case detail, map, and external cues in one quick-glance image for reviewers skimming the submission.
   - **Suggested filename:** `08-submission-cover-collage.png`
