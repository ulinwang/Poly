#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8765}"
TMPDIR="${TMPDIR:-/tmp}"

PASS=0
FAIL=0

http_code() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

assert_ok() {
  local code
  code=$(http_code "$@")
  if [ "$code" = "200" ]; then
    echo "  ✓ $1 -> HTTP $code"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $1 -> HTTP $code (expected 200)"
    FAIL=$((FAIL + 1))
  fi
}

assert_status() {
  local expected="$1"
  shift
  local code
  code=$(http_code "$@")
  if [ "$code" = "$expected" ]; then
    echo "  ✓ $1 -> HTTP $code"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $1 -> HTTP $code (expected $expected)"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== E2E Integration Tests ==="
echo "Base URL: $BASE_URL"
echo ""

# 1. API endpoints
echo "1. Markets API"
assert_ok "$BASE_URL/api/v1/markets"
assert_ok "$BASE_URL/api/v1/markets?q=politics&limit=5"

echo ""
echo "2. Experiments API"
assert_ok "$BASE_URL/api/v1/experiments/stats"
assert_ok "$BASE_URL/api/v1/experiments?limit=10&offset=0"

# Create experiment
CREATE_RESP=$(curl -s -X POST "$BASE_URL/api/v1/experiments" \
  -H "Content-Type: application/json" \
  -d '{"slug":"e2e-test","n_agents":4,"n_ticks":5,"persona_set":"archetype"}')
RUN_ID=$(echo "$CREATE_RESP" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
echo "  Created run_id: $RUN_ID"

assert_status 200 "$BASE_URL/api/v1/experiments/$RUN_ID"

echo ""
echo "3. SSE Events Stream"
EVENTS_FILE=$(mktemp "$TMPDIR/e2e-events.XXXXXX")
curl -sN "$BASE_URL/api/v1/experiments/$RUN_ID/events?replay=0" > "$EVENTS_FILE" &
CURL_PID=$!
sleep 2.5
kill "$CURL_PID" 2>/dev/null || true
if grep -q "event:" "$EVENTS_FILE"; then
  echo "  ✓ SSE stream contains event: lines"
  PASS=$((PASS + 1))
else
  echo "  ✗ SSE stream missing event: lines"
  FAIL=$((FAIL + 1))
fi
rm -f "$EVENTS_FILE"

echo ""
echo "4. Cancel Experiment"
# Create a longer-running experiment to cancel
CREATE_RESP2=$(curl -s -X POST "$BASE_URL/api/v1/experiments" \
  -H "Content-Type: application/json" \
  -d '{"slug":"e2e-cancel","n_agents":4,"n_ticks":200,"persona_set":"archetype"}')
RUN_ID2=$(echo "$CREATE_RESP2" | sed -n 's/.*"run_id":"\([^"]*\)".*/\1/p')
echo "  Created cancel run_id: $RUN_ID2"
sleep 0.3
assert_status 200 -X POST "$BASE_URL/api/v1/experiments/$RUN_ID2/cancel"

echo ""
echo "5. Settings API"
assert_ok "$BASE_URL/api/v1/settings/api"
assert_ok "$BASE_URL/api/v1/settings/general"

echo ""
echo "6. Providers API"
assert_ok "$BASE_URL/api/v1/providers"

echo ""
echo "7. Static File Serving"
assert_ok "$BASE_URL/"

echo ""
echo "8. SPA Fallback"
assert_ok "$BASE_URL/experiments"
assert_ok "$BASE_URL/markets/some-slug"
assert_ok "$BASE_URL/settings"

echo ""
echo "===================="
echo "Passed: $PASS"
echo "Failed: $FAIL"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
echo "All tests passed!"
