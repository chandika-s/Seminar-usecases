"""
Alertmanager → Bedrock AgentCore bridge.

Receives Prometheus Alertmanager webhook POSTs, builds a prompt from the alert payload,
and invokes the configured Bedrock AgentCore runtime. Returns 202 immediately so
Alertmanager does not block on agent execution.
"""

import json
import os
import hmac
import logging
import uuid
from typing import Any

import boto3
from fastapi import FastAPI, Request, HTTPException, Header, Depends
from fastapi.responses import JSONResponse

# Configure logging; do not log sensitive data (tokens, API keys, full alert bodies in production)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Alertmanager AgentCore Bridge",
    description="Receives Alertmanager webhooks and invokes Bedrock AgentCore agent for investigation.",
    version="0.1.0",
)

# Required: set via environment
AGENT_RUNTIME_ARN = os.environ.get("AGENT_RUNTIME_ARN")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
# Optional: if set, webhook requests must include this secret (e.g. in X-Webhook-Secret header)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")


def _build_prompt(payload: dict[str, Any]) -> str:
    """Build an investigation prompt from the Alertmanager webhook payload."""
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


def _validate_webhook_secret(provided: str | None) -> bool:
    """Validate webhook secret using constant-time comparison."""
    if not WEBHOOK_SECRET:
        return True
    if not provided:
        return False
    return hmac.compare_digest(
        WEBHOOK_SECRET.encode("utf-8"), provided.encode("utf-8")
    )


async def verify_webhook(
    request: Request,
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
    authorization: str | None = Header(None),
) -> None:
    """Optional dependency: require valid webhook secret if WEBHOOK_SECRET is set."""
    if not WEBHOOK_SECRET:
        return
    secret = x_webhook_secret
    if not secret and authorization and authorization.startswith("Bearer "):
        secret = authorization[7:].strip()
    if not _validate_webhook_secret(secret):
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")


@app.get("/health")
async def health():
    """Health check for readiness/liveness probes."""
    return {"status": "ok"}


@app.get("/ping")
async def ping():
    """Simple ping for load balancers."""
    return {"pong": True}


@app.post("/webhook")
@app.post("/webhook/alertmanager")
async def webhook(
    request: Request,
    _: None = Depends(verify_webhook),
):
    """
    Receive Alertmanager webhook, build prompt, and invoke AgentCore.
    Returns 202 Accepted immediately; agent runs asynchronously.
    """
    if not AGENT_RUNTIME_ARN:
        raise HTTPException(
            status_code=503,
            detail="AGENT_RUNTIME_ARN not configured",
        )

    try:
        body = await request.json()
    except Exception as e:
        logger.warning("Invalid JSON body: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON body") from e

    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    alerts_count = len(body.get("alerts", []))
    status = body.get("status", "unknown")
    logger.info("Webhook received: status=%s alerts_count=%s", status, alerts_count)

    prompt = _build_prompt(body)
    session_id = str(uuid.uuid4())

    invoke_payload = json.dumps({
        "prompt": prompt,
        "alertmanager_payload": body,
    })

    try:
        client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
        client.invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            qualifier=os.environ.get("AGENT_QUALIFIER", "DEFAULT"),
            runtimeSessionId=session_id,
            payload=invoke_payload,
        )
    except Exception as e:
        logger.exception("Failed to invoke AgentCore")
        raise HTTPException(
            status_code=502,
            detail="Failed to invoke agent runtime",
        ) from e

    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "message": "Alert forwarded to AgentCore for investigation",
            "session_id": session_id,
            "alerts_count": alerts_count,
        },
    )


@app.on_event("startup")
async def startup():
    if not AGENT_RUNTIME_ARN:
        logger.warning("AGENT_RUNTIME_ARN is not set; /webhook will return 503")
    else:
        logger.info(
            "Bridge configured for agentRuntimeArn=%s",
            AGENT_RUNTIME_ARN[:50] + "...",
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
        log_level="info",
    )
