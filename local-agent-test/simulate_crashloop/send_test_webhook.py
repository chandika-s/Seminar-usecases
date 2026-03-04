#!/usr/bin/env python3
"""Send sample Alertmanager payload to the local webhook server. No bash/jq required."""
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

SCRIPT_DIR = Path(__file__).resolve().parent
PAYLOAD_FILE = SCRIPT_DIR / "sample_alertmanager_payload.json"
URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080/webhook"

def main():
    if not PAYLOAD_FILE.exists():
        print(f"Missing {PAYLOAD_FILE}")
        sys.exit(1)
    with open(PAYLOAD_FILE) as f:
        payload = json.load(f)
    print(f"POST {URL}")
    r = requests.post(URL, json=payload, timeout=120)
    r.raise_for_status()
    out = r.json()
    print(json.dumps(out, indent=2))
    if "response" in out:
        print("\n--- Agent response ---\n")
        print(out["response"])

if __name__ == "__main__":
    main()
