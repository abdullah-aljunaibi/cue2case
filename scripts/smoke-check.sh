#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="${API_BASE_URL:-http://localhost:8000}"

echo "Smoke check: ${API_BASE_URL}"

python3 - "$API_BASE_URL" <<'PY'
import json
import sys
import urllib.request

base = sys.argv[1].rstrip('/')

def get_json(path):
    with urllib.request.urlopen(base + path) as resp:
        return json.load(resp)

health = get_json('/health')
assert health['status'] == 'ok', health

cases = get_json('/cases?limit=1')
assert isinstance(cases, list) and len(cases) == 1, cases
case_id = cases[0]['id']
assert case_id, cases[0]
assert 'confidence_score' in cases[0], cases[0]

case_detail = get_json(f'/cases/{case_id}')
assert case_detail['id'] == case_id, case_detail
assert 'evidence' in case_detail, case_detail
assert 'confidence_score' in case_detail, case_detail

map_cases = get_json('/map/cases?limit=1')
assert isinstance(map_cases, list) and len(map_cases) == 1, map_cases
assert map_cases[0]['case_id'] == case_id, map_cases[0]
assert 'confidence_score' in map_cases[0], map_cases[0]

print('OK: /health')
print(f'OK: /cases -> {case_id}')
print('OK: /cases/{uuid}')
print('OK: /map/cases')
PY
