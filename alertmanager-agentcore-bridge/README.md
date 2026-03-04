# Alertmanager AgentCore Bridge

A small HTTP service that receives **Prometheus Alertmanager** webhooks and invokes an **Amazon Bedrock AgentCore** runtime. Use it when you want alerts to trigger an AI agent (e.g. Strands agent with tools) to investigate logs, propose fixes, and suggest remediation.

## Flow

1. Alertmanager sends a `POST` to this service when alerts fire or resolve.
2. The bridge builds a prompt from the webhook payload (status, labels, annotations).
3. It calls `InvokeAgentRuntime` with that prompt and the full payload.
4. The bridge returns `202 Accepted` immediately so Alertmanager does not block.
5. The agent runs in AgentCore and can use tools (logs, runbooks, etc.) to investigate.

## Configuration

Set via environment variables (no secrets in code):

| Variable | Required | Description |
|----------|----------|-------------|
| `AGENT_RUNTIME_ARN` | Yes | ARN of the Bedrock AgentCore runtime (your deployed Strands agent). |
| `AWS_REGION` | No | AWS region for `bedrock-agentcore` (default: `us-east-1`). |
| `AGENT_QUALIFIER` | No | Runtime qualifier (default: `DEFAULT`). |
| `WEBHOOK_SECRET` | No | If set, requests must include this secret in `X-Webhook-Secret` or `Authorization: Bearer <secret>`. |
| `PORT` | No | HTTP port (default: `8080`). |

Copy `.env.example` to `.env` and fill in values (do not commit `.env`).

## Endpoints

- `POST /webhook` or `POST /webhook/alertmanager` — Alertmanager webhook receiver. Body: Alertmanager JSON payload.
- `GET /health` — Health check for Kubernetes readiness/liveness.
- `GET /ping` — Simple liveness.

## Alertmanager configuration

In your Alertmanager config, add a webhook receiver and route to it:

```yaml
receivers:
  - name: 'agentcore-bridge'
    webhook_configs:
      - url: 'http://alertmanager-agentcore-bridge:8080/webhook'
        send_resolved: true
        # Optional: if WEBHOOK_SECRET is set, send in header
        # http_config:
        #   bearer_token: '<your-webhook-secret>'
```

If the bridge is in the same Kubernetes cluster, use the service URL (e.g. `http://alertmanager-agentcore-bridge.<namespace>.svc.cluster.local:8080/webhook`). For bearer token, configure your Alertmanager's webhook_configs with `http_config.bearer_token`; this app also accepts `X-Webhook-Secret: <WEBHOOK_SECRET>`.

## Run locally

```bash
cd alertmanager-agentcore-bridge
pip install -r requirements.txt
export AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:...
python app.py
# Or: uvicorn app:app --host 0.0.0.0 --port 8080
```

Test with a minimal Alertmanager payload:

```bash
curl -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alerts":[{"status":"firing","labels":{"alertname":"Test"},"annotations":{}}]}'
```

## Run as a container (pod/service)

Build and run:

```bash
docker build -t alertmanager-agentcore-bridge .
docker run -p 8080:8080 \
  -e AGENT_RUNTIME_ARN=arn:aws:bedrock-agentcore:... \
  -e AWS_REGION=us-east-1 \
  alertmanager-agentcore-bridge
```

## Kubernetes

Use a **Deployment with multiple replicas** (not a single Pod) for high availability, rolling updates, and no single point of failure. Manifests are in **[`k8s/`](./k8s/)**:

- `namespace.yaml` – dedicated namespace
- `configmap.yaml` – `AWS_REGION`, `AGENT_QUALIFIER`
- `secret.yaml` – `AGENT_RUNTIME_ARN`, optional `WEBHOOK_SECRET` (replace placeholders before apply)
- `serviceaccount.yaml` – for IRSA (IAM Roles for Service Accounts) so pods can call Bedrock AgentCore
- `deployment.yaml` – 2 replicas, liveness/readiness on `/health`, resource limits
- `service.yaml` – ClusterIP on port 8080

See **[`k8s/README.md`](./k8s/README.md)** for apply order, image configuration, and Alertmanager webhook URL.

## Agent payload

The bridge sends to AgentCore a JSON payload with:

- `prompt`: Human-readable summary of the Alertmanager notification (status, group labels, common annotations, and per-alert labels/annotations).
- `alertmanager_payload`: Full Alertmanager webhook JSON so the agent can use raw labels/annotations if needed.

Your Strands entrypoint (e.g. in Lab 5) should read `payload.get("prompt")` for the main instruction and optionally `payload.get("alertmanager_payload")` for structured data.

## Security

- Do not hardcode `AGENT_RUNTIME_ARN` or `WEBHOOK_SECRET` in code; use environment (or a secret store).
- If `WEBHOOK_SECRET` is set, the bridge validates the secret with constant-time comparison.
- Logs avoid sensitive data; only status and alert count are logged from the webhook body.
