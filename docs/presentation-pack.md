# Cue2Case

Explainable port-approach anomaly triage and case-building system for maritime analysts.

## The problem

Maritime monitoring tools are good at showing movement. They are less good at helping an analyst answer the real question: which vessel behaviors deserve attention right now, and why?

In a port-approach setting, raw AIS tracks create noise fast. Operators have to sort through approach patterns, silent periods, loitering, and odd kinematics across many vessels. That makes it easy to miss the handful of cases that matter or waste time on activity that looks suspicious at first glance but has a normal explanation.

## Why current workflows break

Most workflows are still map-first. The analyst starts with dots and lines, then manually reconstructs what happened, then tries to decide whether it should become a case.

That breaks down for three reasons:

- alerts arrive as isolated events rather than analyst-ready cases
- context is scattered across tracks, timelines, and external information
- most systems score behavior without explaining the reasons for or against suspicion

The result is a high review burden and inconsistent triage.

## Our solution

Cue2Case turns raw vessel behavior into explainable, reviewable cases.

Instead of asking an analyst to build a narrative from a map, the system groups related anomalies into a case, attaches suspicious and benign reasoning, preserves spatial context, and leaves room for external cues to change priority. The interface is case-first because that is how an analyst actually works.

## Architecture overview

The pipeline is:

Ingestion → Normalization → Features → Detection → Case Engine → API → UI

At a high level:

- Ingestion collects AIS and external cue inputs.
- Normalization standardizes positions and event records into a consistent shape.
- Features derive behavioral context from vessel movement and geography.
- Detection runs anomaly logic over those features.
- The Case Engine groups alerts into analyst-facing cases with evidence and reasoning.
- The API exposes the data model cleanly to the frontend.
- The UI supports triage, review, and case-building.

## Detector logic summary

### abnormal_approach
Flags approach behavior that deviates from expected port-entry patterns. This is the highest-volume detector and is meant to surface unusual approach geometry or timing early.

### ais_silence
Flags gaps where AIS transmission drops out in a way that may matter operationally. The goal is not to treat every silence as suspicious, but to preserve it as evidence when it overlaps with other signals.

### loitering
Flags vessels that spend unusual time in an area rather than progressing through a normal approach. This helps surface waiting, hovering, or indecisive behavior near operationally relevant zones.

### kinematic_anomaly
Flags motion patterns that do not fit expected speed or maneuver behavior. It is lower-volume by design and acts as a sharper indicator when movement itself looks wrong.

## Product walkthrough

### 1. Queue
The queue page is the operational entry point. It shows the analyst which cases exist, how they are ranked, and where to start. This is the shift away from map-first review toward triage-first review.

### 2. Case detail
The case detail page is where an alert becomes understandable. It combines the evidence timeline with suspicious and benign reasons so the analyst can see both why the system raised the case and what might explain it away.

### 3. Map staging view
The map staging view adds the spatial picture without making the map the whole workflow. It helps the analyst verify approach paths, position relative to geofences, and movement shape in context.

### 4. External cues
The external cues page shows how outside information can enter the workflow. This gives the system a path to incorporate intelligence beyond AIS alone and supports better prioritization.

## Proof / metrics

This prototype is already operating on a non-trivial dataset:

- 333 vessels
- 132,942 AIS positions
- 614 track segments
- 4,470 alerts
- 656 cases
- 3 external cues

Alert distribution:

- abnormal_approach: 3,201
- ais_silence: 833
- loitering: 402
- kinematic_anomaly: 34

Explainability coverage:

- suspicious reasons: 82.8%
- benign reasons: 92.2%
- explanations: 100%
- geofence context: 93.5%

Those numbers matter because they show two things. First, the system is not a toy UI on top of a tiny sample. Second, explainability is built into the output rather than bolted on afterward.

## Why this is valuable to OKB specifically

OKB works on operational systems where signal quality, analyst time, and explainability all matter. Cue2Case fits that reality well.

What I think is relevant here is not just that the prototype detects anomalies. A lot of systems can do that. The stronger point is that it turns detections into analyst-ready case objects with enough context to review quickly and challenge the model when needed.

For OKB, that means:

- a workflow that matches real triage behavior better than raw map review
- a clearer path from anomaly detection to evidence-backed case-building
- explainability that helps operators trust, reject, or escalate a case
- an external cue pathway that can support richer fused workflows later

## Roadmap / next steps

Near-term next steps are practical:

- tighten ranking and prioritization logic across mixed alert types
- improve case grouping quality and analyst controls
- expand external cue ingestion beyond the current three cues
- polish map presentation for live demos and operational review
- run broader evaluation on more traffic and more ports

The prototype already proves the workflow. The next step is making the triage loop sharper and the evidence layer deeper.

## Closing

Cue2Case is my attempt to solve the part of maritime anomaly detection that often gets skipped: what happens after the model fires. The prototype does not just find unusual behavior. It organizes that behavior into cases, explains why they exist, preserves the spatial and temporal evidence, and gives an analyst a place to work. That case-first, explainable approach is the part I would want to keep pushing at OKB.