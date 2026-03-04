"""
Local webhook server: receives Alertmanager payloads and runs the local agent.

Use this to simulate: Alertmanager (or a test curl) sends a CrashLoopBackOff alert
→ this server runs the Strands agent with the alert as context → agent gets pod details,
logs, events and proposes a fix. No AgentCore; runs the same agent as agent.py.
"""

import json
import logging
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request

load_dotenv(Path(__file__).resolve().parent / ".env")

from agent import agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Local Alertmanager Webhook → Agent", version="0.1.0")


def _build_prompt(payload: dict[str, Any]) -> str:
    """Build the same style prompt the bridge would send to the agent."""
    status = payload.get("status", "unknown")
    alerts = payload.get("alerts", [])
    group_labels = payload.get("groupLabels", {})
    common_annotations = payload.get("commonAnnotations", {})
    external_url = payload.get("externalURL", "")

    lines = [
        "A Prometheus Alertmanager webhook was received. Please investigate and propose remediation.",
        f"Overall status: {status}",
        f"Alertmanager URL: {external_url}",
        "",
        "Group labels: " + json.dumps(group_labels),
        "Common annotations: " + json.dumps(common_annotations),
        "",
        "Alerts:",
    ]
    for i, a in enumerate(alerts, 1):
        lines.append(
            f"  [{i}] status={a.get('status')} labels={a.get('labels')} annotations={a.get('annotations')}"
        )
        if a.get("generatorURL"):
            lines.append(f"      generatorURL: {a['generatorURL']}")
    return "\n".join(lines)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
@app.post("/webhook/alertmanager")
async def webhook(request: Request):
    """
    Receive Alertmanager webhook JSON, build prompt, run the local agent, return its response.
    """
    try:
        body = await request.json()
    except Exception as e:
        logger.warning("Invalid JSON: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    alerts_count = len(body.get("alerts", []))
    alerts = body.get("alerts", [])

    # Extract namespace/pod from first alert labels (real payload from Alertmanager)
    alert_context_used = []
    for i, a in enumerate(alerts):
        labels = a.get("labels") or {}
        ns = labels.get("namespace") or labels.get("Namespace") or ""
        pod = labels.get("pod") or labels.get("Pod") or ""
        alertname = labels.get("alertname") or ""
        alert_context_used.append({
            "alert_index": i + 1,
            "alertname": alertname,
            "namespace": ns,
            "pod": pod,
            "status": a.get("status"),
        })
    logger.info(
        "Webhook received: status=%s alerts_count=%s context=%s",
        body.get("status"),
        alerts_count,
        alert_context_used,
    )

    # Skip agent for kube-system and monitoring namespaces (local cluster known issues / stack components)
    namespaces = {ctx["namespace"] for ctx in alert_context_used if ctx.get("namespace")}
    if namespaces == {"kube-system"}:
        response = "Ignored: kube-system namespace (local cluster known issues). No action taken."
        return {
            "status": "ok",
            "alerts_count": alerts_count,
            "alert_context_used": alert_context_used,
            "response": response,
        }
    if namespaces == {"monitoring"}:
        response = "Ignored: monitoring namespace (Prometheus/Alertmanager stack). No action taken."
        return {
            "status": "ok",
            "alerts_count": alerts_count,
            "alert_context_used": alert_context_used,
            "response": response,
        }

    prompt = _build_prompt(body)
    try:
        response = agent(prompt)
    except Exception as e:
        logger.exception("Agent run failed")
        # Return 200 so Alertmanager does not report "sending alerts failed" and retry
        return {
            "status": "agent_failed",
            "alerts_count": alerts_count,
            "alert_context_used": alert_context_used,
            "response": f"Agent run failed: {e!s}",
        }

    return {
        "status": "ok",
        "alerts_count": alerts_count,
        "alert_context_used": alert_context_used,
        "response": str(response),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
