#!/usr/bin/env bash
# Smoke-test the Cue2Case API workflow and map surfaces against a local or overridden base URL.
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "Smoke check: ${API_BASE_URL}"

python3 - "$API_BASE_URL" <<'PY'
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

base = sys.argv[1].rstrip('/')


def fail(message):
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def pass_(message):
    print(f"PASS: {message}")


def require(condition, message):
    if not condition:
        fail(message)


def request_json(method, path, payload=None):
    url = base + path
    body = None
    headers = {"Accept": "application/json"}

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request) as response:
            raw = response.read().decode("utf-8")
            data = json.loads(raw) if raw else None
            return response.status, data
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        fail(f"{method} {path} returned HTTP {exc.code}: {body_text}")
    except urllib.error.URLError as exc:
        fail(f"{method} {path} failed: {exc}")
    except json.JSONDecodeError as exc:
        fail(f"{method} {path} returned invalid JSON: {exc}")


status, health = request_json("GET", "/health")
require(status == 200, "/health did not return HTTP 200")
require(isinstance(health, dict) and health.get("status") == "ok", f"/health unexpected payload: {health}")
pass_("/health")

status, cases = request_json("GET", "/cases/?limit=1")
require(status == 200, "/cases/ did not return HTTP 200")
require(isinstance(cases, list) and len(cases) >= 1, "/cases/ did not return at least one case")
first_case = cases[0]
case_id = first_case.get("id")
require(case_id, f"/cases/ first item missing id: {first_case}")
pass_(f"/cases/ -> first case id {case_id}")

status, case_detail = request_json("GET", f"/cases/{case_id}")
require(status == 200, f"/cases/{case_id} did not return HTTP 200")
require(isinstance(case_detail, dict) and case_detail.get("id") == case_id, f"/cases/{case_id} returned unexpected payload: {case_detail}")
pass_(f"/cases/{case_id}")

patch_payload = {"status": "in_review", "assigned_to": "abdullah"}
status, patched_case = request_json("PATCH", f"/cases/{case_id}", patch_payload)
require(status == 200, f"PATCH /cases/{case_id} did not return HTTP 200")
require(isinstance(patched_case, dict), f"PATCH /cases/{case_id} returned non-object payload: {patched_case}")
require(patched_case.get("status") == "in_review", f"PATCH /cases/{case_id} did not persist status=in_review: {patched_case}")
require(patched_case.get("assigned_to") == "abdullah", f"PATCH /cases/{case_id} did not persist assigned_to=abdullah: {patched_case}")
pass_(f"PATCH /cases/{case_id} set status=in_review and assigned_to=abdullah")

note_payload = {
    "author": "abdullah",
    "content": f"smoke-check note {datetime.now(timezone.utc).isoformat()}",
}
status, note = request_json("POST", f"/cases/{case_id}/notes", note_payload)
require(status == 200, f"POST /cases/{case_id}/notes did not return HTTP 200")
require(isinstance(note, dict), f"POST /cases/{case_id}/notes returned non-object payload: {note}")
require(note.get("case_id") == case_id, f"POST /cases/{case_id}/notes returned wrong case_id: {note}")
require(note.get("author") == note_payload["author"], f"POST /cases/{case_id}/notes returned wrong author: {note}")
require(note.get("content") == note_payload["content"], f"POST /cases/{case_id}/notes returned wrong content: {note}")
pass_(f"POST /cases/{case_id}/notes")

status, audit = request_json("GET", f"/cases/{case_id}/audit")
require(status == 200, f"GET /cases/{case_id}/audit did not return HTTP 200")
require(isinstance(audit, list) and len(audit) >= 1, f"GET /cases/{case_id}/audit returned no entries: {audit}")
pass_(f"GET /cases/{case_id}/audit -> {len(audit)} entries")

status, map_cases = request_json("GET", "/map/cases?limit=1")
require(status == 200, "/map/cases did not return HTTP 200")
require(isinstance(map_cases, list) and len(map_cases) >= 1, "/map/cases did not return at least one item")
first_map_case = map_cases[0]
for field in ("rank_score", "status", "lon", "lat"):
    require(field in first_map_case, f"/map/cases first item missing {field}: {first_map_case}")
pass_("/map/cases includes rank_score, status, lon, lat")

print("PASS: smoke suite complete")
PY
