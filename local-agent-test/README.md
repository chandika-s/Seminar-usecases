# Local Agent Test (Docker Desktop K8s)

A minimal Strands agent that talks to your **local** Kubernetes cluster (e.g. Docker Desktop) to list pods and get pod logs. Use this to validate the agent + K8s flow before running the full EKS demo.

## Prerequisites

- **Docker Desktop** with Kubernetes enabled (or any local cluster).
- **kubeconfig** pointing at that cluster (default: `~/.kube/config` or set `KUBECONFIG`).
- **OpenAI API key** (personal or org). No Bedrock/AWS required.

## Setup

```bash
cd local-agent-test
pip install -r requirements.txt
```

Set your OpenAI API key in `.env` (do not commit `.env`):

```
OPENAI_API_KEY=sk-...
```

Optional in `.env`: use a different model (default is `gpt-4o-mini`):

```
OPENAI_MODEL_ID=gpt-4o
```

## Run

**CLI – one-shot prompt:**

```bash
python agent.py "List pods in the default namespace"
python agent.py "Get logs for pod myapp-abc123 in namespace default"
python agent.py "What pods are in namespace kube-system? Then get the last 50 lines of logs for one of them."
```

**Interactive (Python):**

```python
from agent import agent

# List pods
agent("List all pods in default namespace")

# Get logs (use a real pod name from your cluster)
agent("Get the last 100 lines of logs for pod <POD_NAME> in namespace default")
```

## What the agent can do

**Investigation:** `k8s_list_pods`, `k8s_get_logs`, `k8s_describe_pod`, `k8s_get_events`.

**Auto-fix (when safe):** For OOMKilled the agent can patch the Deployment memory limit and run a rollout restart. For transient restarts it can run a rollout restart only. Tools: `k8s_get_deployment`, `k8s_patch_deployment_resources`, `k8s_rollout_restart`. Optional env: `K8S_MAX_MEMORY_LIMIT_MB` (default 2048).

**Escalation (when it cannot fix):** For CreateContainerConfigError, missing env, or unknown cause the agent creates a JIRA ticket and sends a Slack notification. Tools: `create_jira_ticket`, `send_slack_notification`. Set `JIRA_BASE_URL`, `JIRA_PROJECT_KEY`, `JIRA_EMAIL`, `JIRA_API_TOKEN` and/or `SLACK_WEBHOOK_URL` in `.env` (see `.env.example`). If unset, the agent still reports what it would have done.

The agent uses your default kubeconfig and OpenAI; no EKS IAM or proxy.

## Simulate CrashLoopBackOff → Webhook → Agent investigates and proposes fix

End-to-end flow: trigger a webhook (like Alertmanager would), run the local agent with the alert, and get a proposed fix.

### 1. Deploy a pod that crashes (CrashLoopBackOff)

```bash
kubectl apply -f simulate_crashloop/crash-pod.yaml
# Wait a few seconds; pod will be in CrashLoopBackOff
kubectl get pods -n default
```

### 2. Start the webhook server

In one terminal:

```bash
cd local-agent-test
python webhook_server.py
# Listens on http://0.0.0.0:8080
```

### 3. Send a test webhook (simulated Alertmanager)

In another terminal:

```bash
cd local-agent-test
python simulate_crashloop/send_test_webhook.py
# Or: ./simulate_crashloop/send_test_webhook.sh
# Default URL: http://localhost:8080/webhook
```

The server receives the Alertmanager-style payload, runs the agent with the alert context (namespace `default`, pod `crashloop-demo`). The agent will:

- List pods in `default`, get logs and describe `crashloop-demo`, get namespace events
- Identify the cause (e.g. container exits with code 1)
- Recommend a fix (e.g. fix the image/command, or delete the pod to recreate). It does not execute any changes.

The response is returned in the HTTP body (`response` field).

### 4. Alertmanager webhook receiver (real alerts)

**Webhook URL to put in Alertmanager:**

- **Alertmanager in cluster (e.g. Docker Desktop):**  
  `http://host.docker.internal:8080/webhook`  
  (Mac/Windows; Linux use your host IP, e.g. `http://192.168.1.100:8080/webhook`.)
- **Alertmanager on same host as webhook server:**  
  `http://localhost:8080/webhook`

Start the webhook server on your host first: `python webhook_server.py` (binds to `0.0.0.0:8080`).

**Config:** Add a webhook receiver to your existing Alertmanager config. See **`alertmanager-webhook-receiver.example.yaml`** for a copy-paste snippet. Add the receiver and point a route (e.g. for `CrashLoopBackOff` or your demo app alerts) to it; you can keep your email receiver and use `continue: true` so alerts go to both.

**Flow:** Alertmanager POSTs the real alert payload to this URL → webhook server builds a prompt from it → agent runs and uses **namespace/pod from the alert labels** to call the tools (list pods, get logs, describe pod, get events) against your cluster → response is returned.

### 5. Verifying the agent did real work

- **`alert_context_used`** in the webhook response lists what was taken from the POST payload (alertname, namespace, pod per alert). That confirms the agent was triggered with your real alert.
- **`response`** is the agent's full reply. It will include real cluster data (pod names, log snippets, events, describe output) and a recommended fix only if the agent actually called the tools against your cluster. If the namespace/pod from the alert exist, the reply will reflect real logs and events; if not, the agent will say so. Use that to confirm the agent did a real investigation.

### 6. Clean up crash pod

```bash
kubectl delete -f simulate_crashloop/crash-pod.yaml
```
