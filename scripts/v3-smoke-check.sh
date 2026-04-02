#!/usr/bin/env bash
# Validate the core Cue2Case v3 API endpoints and a basic case workflow path.
set -uo pipefail

API="${API_URL:-http://localhost:8000}"
PASS=0
FAIL=0

check() {
  local desc="$1" url="$2" expected="$3"
  local body status
  body=$(curl -sf "$url" 2>/dev/null) && status=0 || status=1
  if [ $status -eq 0 ] && echo "$body" | grep -qF "$expected"; then
    echo "  ✅ $desc"
    ((PASS++))
  else
    echo "  ❌ $desc (expected: $expected)"
    ((FAIL++))
  fi
}

echo "=== Cue2Case v3 Smoke Check ==="
echo ""
echo "Core endpoints:"
check "Health" "$API/" "cue2case"
check "Cases list" "$API/cases/?limit=3" "rank_score"
check "Port profile" "$API/port-context/profile" "duqm"

echo ""
echo "Duqm scenarios:"
CASE_ID=$(curl -sf "$API/cases/?limit=1" | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])" 2>/dev/null || echo "")
if [ -n "$CASE_ID" ]; then
  check "Case detail" "$API/cases/$CASE_ID" "score"
  check "Score breakdown" "$API/cases/$CASE_ID/score" "why_now"
  check "Replay" "$API/cases/$CASE_ID/replay" "events"
  check "Notes" "$API/cases/$CASE_ID/notes" "["
  check "Audit" "$API/cases/$CASE_ID/audit" "["
else
  echo "  ⚠️  No cases found, skipping detail checks"
  ((FAIL+=5))
fi

echo ""
echo "Workflow:"
if [ -n "$CASE_ID" ]; then
  ACTION_RESP=$(curl -sf -X POST "$API/cases/$CASE_ID/actions" \
    -H "Content-Type: application/json" \
    -d '{"action":"acknowledge","actor":"smoke-test"}' 2>/dev/null || echo "")
  if echo "$ACTION_RESP" | grep -q "audit_logged"; then
    echo "  ✅ Workflow action (acknowledge)"
    ((PASS++))
  else
    echo "  ❌ Workflow action"
    ((FAIL++))
  fi
fi

echo ""
echo "Port context:"
check "Zone criticality" "$API/port-context/criticality?lon=57.68&lat=21.65" "criticality"
check "Zone lookup" "$API/port-context/zones?lon=57.68&lat=21.65" "["

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
