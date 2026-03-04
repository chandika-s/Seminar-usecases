# Alertmanager → Bedrock AgentCore DevOps Demo

This repo contains a DevOps demo: when Prometheus Alertmanager fires an alert (e.g. CrashLoopBackOff), an AI agent investigates the Kubernetes cluster, gathers logs and events, and recommends a fix.

## Components

| Component | Description |
| --------- | ----------- |
| **local-agent-test/** | Strands agent + local webhook server. Receives Alertmanager-style webhooks, runs the agent against your local K8s (e.g. Docker Desktop) to list pods, get logs, describe pods, and get events. The agent recommends a fix (no automatic execution). Uses OpenAI; see `local-agent-test/README.md`. |
| **alertmanager-agentcore-bridge/** | HTTP service that receives Alertmanager webhooks and invokes a Bedrock AgentCore agent via `InvokeAgentRuntime`. Deploy this in Kubernetes (e.g. EKS) and point Alertmanager at it when you want the agent to run in AgentCore instead of locally. See `alertmanager-agentcore-bridge/README.md`. |

## Quick start (local)

1. **Run the agent and webhook server** (Docker Desktop K8s or any local cluster):

   ```bash
   cd local-agent-test
   pip install -r requirements.txt
   # Set OPENAI_API_KEY in .env
   python webhook_server.py
   ```

2. **Point Alertmanager** at `http://<host>:8080/webhook` (from the cluster use host IP or `host.docker.internal` on Mac/Windows).

3. **Trigger a test** using the sample payload:

   ```bash
   cd local-agent-test
   python simulate_crashloop/send_test_webhook.py
   ```

See **local-agent-test/README.md** for CrashLoopBackOff simulation, Alertmanager config, and verification steps.

## License

See [LICENSE](LICENSE).
