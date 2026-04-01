# Interview talking points

## Core message

- Cue2Case is a case-first maritime analysis product. It turns raw vessel activity and external cues into investigator-ready cases instead of making analysts hunt through a map.
- The product already covers the full pipeline: ingest data, segment tracks, generate alerts, group them into cases, and explain why each case matters.
- Explainability is built into the workflow. The system gives suspicious reasons, benign reasons, and geofence context so analysts can understand why something was surfaced.
- The strongest product decision was choosing analyst workflow over map novelty. I cared more about helping someone reach a defensible case than about building a prettier live view.
- It is a strong prototype, not a production system. The idea is solid, the workflow works, and the weakest area is still ranking.

## 30-second answer: What is Cue2Case?

Cue2Case is a maritime investigation product that starts from the question an analyst actually has: what deserves a case right now? Instead of leading with a map, it takes AIS activity and external cues, turns them into alerts, groups them into cases, and explains both the suspicious and benign reasons behind each one. In this demo dataset, that pipeline ran across 333 vessels, 132,942 AIS positions, 614 track segments, 4,470 alerts, and 656 cases.

## 60-second answer: Why did you build it this way?

I built it case-first because that is where analyst time gets won or lost. A map is useful, but a map-first workflow still pushes the human to sift through motion, guess what matters, and manually build a narrative. I wanted the product to do more of that work up front.

So the system takes the raw vessel stream, segments it, generates alerts, brings in three external cues, and assembles candidate cases. Then it explains the result in plain operational terms: what looks suspicious, what might be benign, and what geofence context applies. That matters because false positives are unavoidable in this kind of work. The goal is not to pretend they disappear. The goal is to surface them in a way an analyst can audit quickly.

The result is an end-to-end prototype that shows the product judgment clearly. It is not just detection. It is a workflow for getting from cues to a defensible case.

## What to emphasize

- The product choice: case-first, not map-first.
- End-to-end pipeline exists and works on a real demo dataset.
- Explainability is not an afterthought; every case carries reasons and context.
- The system does not only say why something looks suspicious. It also shows benign explanations, which is critical for analyst trust.
- Coverage numbers are concrete: 333 vessels, 132,942 AIS positions, 614 track segments, 4,470 alerts, 656 cases, and 3 external cues.
- Explanation coverage is strong in the current prototype: suspicious reasons at 82.8%, benign reasons at 92.2%, explanations at 100%, and geofence context at 93.5%.
- The project shows product judgment as much as modeling work. The key point is choosing the right unit of work for the analyst.

## What to be honest about

- Ranking is still the softest area. The system can produce cases, but ordering the most important ones is where I would push hardest next.
- Detector maturity is uneven. Some detectors are much more convincing than others.
- External cues are a real pathway in the product, but they are not deep fusion yet.
- This is prototype-grade, not production-ready.
- The value is already clear, but hardening, calibration, and operational validation would still be needed before real deployment.

## Strong answers to likely questions

### Why case-first instead of map-first?

- Because analysts do not get judged on how long they stare at a map. They get judged on whether they can produce a useful case.
- A map is a good interface for exploration. It is a weak primary unit of work if the user needs prioritization, context, and a narrative.
- Case-first let me organize the product around decisions, not just visualization.

### How do you handle false positives?

- I assume they will exist, so the design tries to make them cheap to inspect.
- Each case can carry suspicious reasons and benign reasons, which gives the analyst a fast way to challenge the system instead of blindly trusting it.
- The product goal is not perfect certainty. It is faster triage with clearer reasoning.

### What makes this explainable?

- The system exposes why a case was surfaced, not just a score.
- It includes suspicious reasons, benign reasons, and geofence context.
- In the current prototype, explanations are present for 100% of cases, with suspicious reasons at 82.8%, benign reasons at 92.2%, and geofence context at 93.5%.

### How would you improve it next?

- First, improve ranking. That is the highest-leverage product improvement.
- Second, bring the weaker detectors up to a more consistent level.
- Third, push external cues beyond the current pathway and toward deeper fusion with the rest of the case-building logic.
- After that, I would focus on calibration, analyst feedback loops, and production hardening.

### Is it production-ready?

- No. I would describe it as a strong prototype.
- The workflow is real and the end-to-end story is there, but it still needs better ranking, more consistent detector quality, and production hardening.
- What I would defend strongly is the product direction and the shape of the solution.

## One-paragraph close

If I had to sum it up simply, Cue2Case is my attempt to build the right product unit for maritime analysis. I did not want to stop at alerts or build another map-heavy interface that leaves the hard judgment to the analyst. I wanted a system that can take raw activity and external cues, turn them into cases, and explain the reasoning well enough that a human can move faster without giving up skepticism. It is not production-ready yet, but the core bet feels right.
