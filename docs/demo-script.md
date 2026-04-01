# Cue2Case demo script

## Opening framing (30-45 sec)

Today I want to show Cue2Case, an explainable port-approach anomaly triage and case-building system.

The problem I was trying to solve is pretty simple: maritime tools usually make it easy to see traffic, but much harder to decide what deserves analyst attention. You end up with lots of tracks, lots of alerts, and too much manual reconstruction.

So the core idea here is to move from a map-first workflow to a case-first workflow. Instead of starting with raw vessel movement and building the story by hand, Cue2Case groups signals into reviewable cases, adds reasoning, and keeps the spatial context available when you need it.

## Queue page walkthrough

This is the queue page. This is where an analyst starts.

What I want to show here is the workflow choice: the first object in the system is the case, not the vessel track. That matters because triage is really a prioritization problem before it is a visualization problem.

A few beats to call out:

- the queue gives you a compact list of cases rather than a wall of alerts
- each row is meant to answer: should I open this case now or not?
- this is the point where the system reduces review load by grouping related activity up front

If I were narrating this live, I would say: instead of dropping an analyst onto a busy map and asking them to hunt, I am giving them an ordered worklist.

## Case detail walkthrough

Once I open a case, this is the main review surface.

The case detail page is where the system needs to earn trust. It is not enough to say something is anomalous. The analyst needs to see the evidence and understand the logic.

Here I would walk through:

- the evidence timeline, which reconstructs what happened over time
- the suspicious reasons, which explain why the case was raised
- the benign reasons, which explain what might reduce concern
- the case structure itself, which turns multiple alerts into one reviewable object

This suspicious-versus-benign split is important. It makes the output more useful than a generic anomaly score because it gives the analyst something to agree with, disagree with, or investigate further.

## Map / spatial context walkthrough

Next I move to the map staging view.

I want to be clear about the design choice here: the map is still important, but it is supporting evidence, not the whole workflow.

On this screen I would show:

- the vessel path in space
- how the movement relates to port approach behavior
- any geofence context available for the case
- whether the shape of movement supports the alert narrative

This is where the analyst can sanity-check the case fast. Did the vessel approach in an unusual way? Did it loiter in a place that matters? Did the movement pattern line up with the written explanation?

## External cue walkthrough

After that, I would open the external cues page.

This part is important because AIS alone is rarely enough. Real operational workflows benefit from outside information that can shift priority or add context.

The point of this page is not that it already has huge cue coverage. Right now there are 3 external cues in the prototype. The point is that the ingestion path exists and is wired into the product shape.

The beats I would hit are:

- external information has a clear place in the workflow
- cues can enrich or re-rank a case
- the system is built for fusion, not just standalone track anomaly detection

## Evaluation / proof walkthrough

Then I would close the demo with the current proof points.

The prototype is running on:

- 333 vessels
- 132,942 AIS positions
- 614 track segments
- 4,470 alerts
- 656 cases
- 3 external cues

Detector distribution is also useful to show because it tells you what the system is actually surfacing:

- abnormal_approach: 3,201
- ais_silence: 833
- loitering: 402
- kinematic_anomaly: 34

And for explainability coverage:

- suspicious reasons: 82.8%
- benign reasons: 92.2%
- explanations: 100%
- geofence context: 93.5%

What I would say here is: this is already enough data to test whether the workflow holds up. The prototype is not pretending to be production-complete, but it does show that the case engine, reasoning layer, and UI all work together on a meaningful sample.

## Closing pitch

The bet behind Cue2Case is that anomaly detection gets more useful when it is shaped around analyst decisions instead of raw model output.

What I built here is not just a detector dashboard. It is a case-first review flow with evidence, explainability, geofence-aware context, and a path for external cues.

If I were taking this further, I would focus on ranking quality, stronger case grouping, broader cue ingestion, and final polish on the live presentation layer. But I think the core product decision is already the right one: help the analyst answer "what should I review, and why?" before asking them to interpret the map.