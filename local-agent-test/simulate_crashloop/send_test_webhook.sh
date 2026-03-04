#!/usr/bin/env bash
# Send a sample Alertmanager payload to the local webhook server.
# Start the webhook server first: python webhook_server.py
# Optionally deploy the crash pod first: kubectl apply -f crash-pod.yaml
# Then run: ./send_test_webhook.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PAYLOAD="${SCRIPT_DIR}/sample_alertmanager_payload.json"
URL="${1:-http://localhost:8080/webhook}"

if [[ ! -f "$PAYLOAD" ]]; then
  echo "Missing $PAYLOAD"
  exit 1
fi

echo "POST $URL"
curl -s -X POST "$URL" \
  -H "Content-Type: application/json" \
  -d @"$PAYLOAD" | jq .
