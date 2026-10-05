#!/bin/sh
set -u

mkdir -p /logs/verifier /app

# Discard anything an earlier process may have planted in grader-looking paths.
rm -f \
  /logs/verifier/reward.txt \
  /logs/verifier/ctrf.json \
  /logs/verifier/verdict.json \
  /logs/verifier/score.json \
  /logs/verifier/report.json \
  /logs/verifier/results.json \
  /logs/verifier/result.json \
  /logs/verifier/PASSED \
  /logs/verifier/status 2>/dev/null || true

printf '0\n' > /logs/verifier/reward.txt

status=1
if pytest -q /tests/test_verify.py --ctrf=/logs/verifier/ctrf.json; then
  status=0
fi

if [ "$status" -eq 0 ]; then
  tmp="$(mktemp /logs/verifier/.reward.XXXXXX)" || exit 0
  printf '1\n' > "$tmp"
  mv -f "$tmp" /logs/verifier/reward.txt
else
  tmp="$(mktemp /logs/verifier/.reward.XXXXXX)" || exit 0
  printf '0\n' > "$tmp"
  mv -f "$tmp" /logs/verifier/reward.txt
fi

# These names are never authoritative; do not leave spoofable side reports behind.
rm -f \
  /logs/verifier/verdict.json \
  /logs/verifier/score.json \
  /logs/verifier/report.json \
  /logs/verifier/results.json \
  /logs/verifier/result.json \
  /logs/verifier/PASSED \
  /logs/verifier/status 2>/dev/null || true

exit 0
