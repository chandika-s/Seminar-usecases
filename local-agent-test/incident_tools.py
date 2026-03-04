"""
Incident report tool: create a structured incident (webhook or file). Config via env.
"""

import json
import logging
import os
from datetime import datetime, timezone

from strands import tool

logger = logging.getLogger(__name__)

INCIDENT_REPORT_WEBHOOK_URL = os.environ.get("INCIDENT_REPORT_WEBHOOK_URL", "")
INCIDENT_REPORT_FILE_PATH = os.environ.get("INCIDENT_REPORT_FILE_PATH", "")


@tool
def create_incident_report(
    title: str,
    summary: str,
    details: str,
    severity: str = "medium",
    alert_context: str = "",
) -> str:
    """
    Create an incident report with title, summary, details, and severity (low/medium/high/critical).
    Optionally include alert_context (e.g. namespace, pod, alertname). The report is sent to
    INCIDENT_REPORT_WEBHOOK_URL (POST JSON) or appended to INCIDENT_REPORT_FILE_PATH. If neither
    is set, returns a structured summary for the response.
    """
    report = {
        "title": title,
        "summary": summary,
        "details": details,
        "severity": severity.lower() if severity else "medium",
        "alert_context": alert_context,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if INCIDENT_REPORT_WEBHOOK_URL:
        try:
            import requests
            r = requests.post(
                INCIDENT_REPORT_WEBHOOK_URL,
                json=report,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            r.raise_for_status()
            return json.dumps({"status": "sent", "webhook": INCIDENT_REPORT_WEBHOOK_URL})
        except Exception as e:
            logger.warning("Incident webhook failed: %s", e)
            return json.dumps({"error": str(e)})
    if INCIDENT_REPORT_FILE_PATH:
        try:
            with open(INCIDENT_REPORT_FILE_PATH, "a") as f:
                f.write(json.dumps(report) + "\n")
            return json.dumps({"status": "written", "path": INCIDENT_REPORT_FILE_PATH})
        except Exception as e:
            logger.warning("Incident file write failed: %s", e)
            return json.dumps({"error": str(e)})
    return json.dumps({"status": "created", "report": report})
