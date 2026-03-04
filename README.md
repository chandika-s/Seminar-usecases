# Alertmanager → Bedrock AgentCore DevOps Demo

This repo contains a DevOps demo: when Prometheus Alertmanager fires an alert (e.g. CrashLoopBackOff), an AI agent investigates the Kubernetes cluster, gathers logs and events, and recommends a fix.

## Components

| Component | Description |
| --------- | ----------- |
| **local-agent-test/** | Strands agent + local webhook server. Receives Alertmanager webhooks, runs the agent against your local K8s (e.g. Docker Desktop). The agent can auto-fix (e.g. OOM memory patch + rollout restart) or escalate (JIRA + Slack). Uses OpenAI; see `local-agent-test/README.md`. |
| **agentcore/** | Agent code for **Amazon Bedrock AgentCore Runtime**. Same troubleshooting logic as local-agent-test, adapted for direct code deployment to AgentCore. See `agentcore/README.md`. |
| **webhook-server/** | Docker image and EKS manifests for the webhook server. Build and run the webhook in a container on EKS; app code lives in `local-agent-test/`. See `webhook-server/README.md`. |

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
