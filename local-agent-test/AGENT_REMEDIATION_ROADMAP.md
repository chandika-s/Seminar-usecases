# Agent Remediation: Auto-Fix, Escalation, and Production Workflow

This document answers design questions for extending the Alertmanager → Webhook → Agent flow: when the agent should **apply fixes automatically**, when it should **escalate (JIRA + Slack)**, which **use cases to demo**, and how to shape a **production-level workflow**. It aligns with the roadmap: Bedrock AgentCore runtime, containerized webhook on EKS, and simulated E2E errors.

---

## Who handles what: webhook vs agent

**Webhook server** has a single responsibility:

1. Receive the POST from Alertmanager.
2. Build the prompt (alert context: namespace, pod, labels, etc.).
3. Invoke the agent (local Strands agent today; Bedrock AgentCore API later).
4. Return (or log) the agent’s response.

The webhook server does **not** decide “auto-fix vs escalate” and does **not** call JIRA or Slack or Kubernetes patch APIs. It only triggers the agent.

**The agent** is the one that performs all further actions. It has **tools**. In one run:

1. Agent uses **read-only tools** (e.g. `k8s_list_pods`, `k8s_get_logs`, `k8s_describe_pod`, `k8s_get_events`) to investigate.
2. Agent decides from the data: **auto-fix** (e.g. OOM) or **escalate** (e.g. missing secret).
3. **If auto-fix:** agent calls **action tools** (e.g. `k8s_patch_deployment_resources`, `k8s_rollout_restart`) in the same run. Those tools run in the same process as the agent; they patch the cluster.
4. **If escalate:** agent calls **escalation tools** (e.g. `create_jira_ticket`, `send_slack_notification`) in the same run. Those tools run in the same process; they create the ticket and send the Slack message.

So: **escalation (and auto-fix) are implemented as tools the agent invokes**. The webhook stays thin; all “further course of action” is done inside the agent run by the agent calling its tools.

```
Alertmanager → Webhook (receive, build prompt, invoke agent) → Agent
                                                                  ├── investigate (k8s_* read tools)
                                                                  ├── decide: auto_fix | escalate
                                                                  ├── if auto_fix: k8s_patch_*, k8s_rollout_restart
                                                                  └── if escalate: create_jira_ticket, send_slack_notification
```

**How to implement:** Add the new tools to the same agent (in `k8s_tools.py` or a separate `remediation_tools.py` / `escalation_tools.py`). Register them with the agent. Update the system prompt so the agent is instructed to call the right tools after diagnosis. No change to the webhook’s role.

---

## 1. Auto-apply fixes (agent applies changes where safe)

**Principle:** The agent should **apply** changes only when the fix is **deterministic, reversible, and low-risk**. Otherwise it should recommend only or escalate.

### Cases suitable for auto-apply

| Scenario | Root cause | Agent action (auto-apply) | Notes |
|----------|------------|---------------------------|--------|
| **OOMKilled** | Container exceeded memory limit | Patch Deployment/StatefulSet: increase `resources.limits.memory` (e.g. +50% or to a configured max), then rollout restart | Need tool: get workload spec, patch resources, optional rollout restart |
| **ImagePullBackOff** (wrong tag) | Image tag typo or known-good tag | Patch Deployment: set `spec.template.spec.containers[].image` to corrected tag if there is a clear pattern (e.g. `latest` or a known alias) | Only if you have a safe rule (e.g. “use :latest when tag invalid”); otherwise recommend only |
| **Restart loop (no OOM)** | Liveness probe too aggressive | Patch Deployment: relax liveness (e.g. increase `initialDelaySeconds` or `failureThreshold`) within allowed bounds | Use configurable min/max to avoid dangerous values |
| **Too many restarts (transient)** | No clear config error | **Rollout restart** only (no spec change) to clear transient state | Safe; agent can call `kubectl rollout restart deploy/<name>` |

### Implementation outline for OOM (and similar)

- **New tools for the agent:**
  - `k8s_get_deployment(namespace, name)` – return Deployment spec (containers, resources).
  - `k8s_patch_deployment_resources(namespace, deployment_name, container_name, memory_limit, memory_request)` – patch `resources.limits.memory` and optionally `requests` for a container.
  - `k8s_rollout_restart(namespace, kind, name)` – e.g. restart Deployment/StatefulSet.
- **Agent prompt rules:**
  - If diagnosis is **OOMKilled** and the workload is a Deployment/StatefulSet: call get deployment → patch memory (e.g. increase by 50% or to a cap) → rollout restart. Then respond with what was changed.
  - Do **not** auto-apply if workload is not found or is a custom resource the agent doesn’t support.
- **Safety:** Enforce maximum memory cap (e.g. via tool or env) so the agent cannot set limits above a safe value.

---

## 2. Escalation when agent cannot fix (JIRA + Slack)

**Principle:** When the agent **cannot** safely apply a fix (e.g. missing secret/env, unknown config, or policy says “no auto-apply”), it should **create a JIRA ticket** and send a **Slack notification** with context so humans can act.

### Cases for escalation (no auto-apply)

| Scenario | Why agent shouldn’t fix | Escalation |
|----------|--------------------------|------------|
| **CreateContainerConfigError** (missing Secret/ConfigMap) | Agent doesn’t know which secret or key is correct | JIRA ticket + Slack: include namespace, pod, error message, and that “secret/config missing” |
| **CrashLoopBackOff** (missing env var) | Agent doesn’t know the correct value (e.g. `VAR_X`) | JIRA + Slack: include logs, pod name, and “missing or invalid env” |
| **ImagePullBackOff** (auth/registry) | Fix requires credentials or registry change | JIRA + Slack: “registry/auth issue – manual intervention required” |
| **Unknown / ambiguous** | Logs don’t match a known pattern | JIRA + Slack: attach summary + logs/events for triage |

### Implementation outline

- **New tools (implemented as agent tools, same as k8s_tools):**
  - `create_jira_ticket(title, description, labels, severity)` – create issue with alert summary, namespace, pod, logs snippet, and agent conclusion (“cannot auto-fix: missing secret”).
  - `send_slack_notification(channel, message, severity)` – send short alert summary and link to JIRA (if created).
- **Agent prompt rules:**
  - After investigation, classify: **auto-fix** (OOM, safe rollout, etc.) vs **escalate**.
  - If **escalate**: call `create_jira_ticket` with a structured description, then `send_slack_notification` with summary and JIRA key. Response should say “No automatic fix applied; JIRA ticket PROJ-123 and Slack notification sent.”
- **Configuration:** JIRA project/key, Slack channel and webhook (or Bot token), and severity mapping (e.g. firing = high) from env or config. The tools read these from env when the agent calls them; no logic in the webhook.

---

## 3. Use cases to show “agent fixes without manual intervention”

These are **demo-friendly** and show the agent **actually applying** a fix end-to-end (good for audience).

| # | Use case | Trigger | What audience sees |
|---|----------|--------|---------------------|
| 1 | **OOMKilled** | Deploy a pod with very low memory limit; process OOMs | Agent gets alert → gets logs/describe → sees OOMKilled → patches Deployment memory limit → rollout restart → pod comes up. No human step. |
| 2 | **Liveness too aggressive** | Set liveness probe that fails under load | Agent diagnoses from logs/events → patches Deployment to relax liveness (e.g. `failureThreshold` or `initialDelaySeconds`) → rollout restart → recovery. |
| 3 | **Transient restart storm** | No spec change needed; just flaky node or network | Agent sees many restarts but no clear config error → runs **rollout restart** only → new pods scheduled → alert clears. |
| 4 | **ImagePullBackOff (tag fix)** | Use a typo tag (e.g. `demo-app:latets`) and a rule “use :latest on pull error” | Agent detects ImagePullBackOff → patches image to `demo-app:latest` (or configured tag) → rollout. Only if you explicitly allow this rule. |

**Suggested demo order:** Start with **OOMKilled** (clear cause/effect, easy to explain), then **rollout restart** (no spec change), then **liveness** if you have it. Keep **CreateContainerConfigError / missing env** for the **escalation** demo (JIRA + Slack, no auto-fix).

---

## 4. Workflow feedback and production-level suggestions

### Is the current workflow fine?

The flow **Alertmanager → Webhook → Agent (investigate → propose)** is a good base. For production you’re right to add:

- **Auto-apply** for a small, well-defined set of cases (OOM, safe rollout, maybe liveness).
- **Escalation** (JIRA + Slack) when the agent cannot or must not apply a fix.

### Production-level workflow suggestions

1. **Explicit classification in the agent**
   - After tools run, agent outputs a **structured conclusion**: `action_type: auto_fix | recommend_only | escalate`.
   - Webhook server or a small middleware can:
     - On `auto_fix`: log what was applied and optionally fire a low-severity “remediated” event.
     - On `escalate`: ensure JIRA + Slack were called (e.g. from agent tools), and optionally retry or alert if those calls fail.

2. **Rate limiting and deduplication**
   - Same alert can fire repeatedly. Optionally:
     - Dedupe by (alertname, namespace, pod) in a short window (e.g. 5–10 min) so the agent doesn’t patch the same Deployment 10 times.
     - Rate-limit agent invocations per namespace or per alert.

3. **Approval / dry-run for risky actions (optional)**
   - For “patch deployment” actions, you can support a **dry_run** mode (agent returns the patch it would apply; a human or automated policy approves it). For the seminar, full auto-apply for OOM is fine; for production, dry-run or approval gates are an option.

4. **Observability**
   - Log every webhook, agent run, and **action taken** (patch, JIRA, Slack). When you move to Bedrock AgentCore runtime, use its observability (traces, sessions) so you can show “this alert led to this tool call and this fix.”

5. **Safe defaults**
   - Memory cap for OOM fixes, allowed namespaces (e.g. don’t auto-patch in `kube-system`), and a list of “allowed for auto-fix” Deployments/StatefulSets if you want to restrict scope.

6. **Webhook server on EKS**
   - Run the webhook server as a Deployment behind a Service; use Ingress or a LoadBalancer so Alertmanager (in or out of cluster) can reach it. No change to the high-level flow; only deployment and scaling.

---

## 5. Alignment with your roadmap

| Step | Suggestion |
|------|------------|
| **Deploy agent in AWS Bedrock AgentCore runtime** | Move agent logic + tools to an AgentCore agent; webhook server becomes a thin client that forwards Alertmanager payload to AgentCore (invoke agent API with the same prompt you build today). |
| **Containerize webhook server and deploy on EKS** | Same FastAPI app; add health checks and resource limits; use EKS IAM for Bedrock (and optionally K8s API if agent runs in cluster). |
| **Simulate errors for E2E** | Use your existing patterns (OOM, CrashLoopBackOff, CreateContainerConfigError, ImagePullBackOff, readiness) from `app/simulation.md`; add one “auto-fix” path (OOM) and one “escalation” path (missing secret) so the audience sees both behaviors. |

---

## Next implementation steps (summary)

All of the following are implemented **in the agent** (new tools + prompt); the webhook server stays as-is (receive → build prompt → invoke agent → return response).

1. **Auto-fix (OOM):** Add agent tools `k8s_get_deployment`, `k8s_patch_deployment_resources`, `k8s_rollout_restart`; update agent system prompt to apply memory patch + restart when OOMKilled is detected.
2. **Escalation:** Add agent tools `create_jira_ticket` and `send_slack_notification` (e.g. in `escalation_tools.py`); update agent prompt to call them when classification is “escalate” (e.g. missing secret/env, unknown cause).
3. **Structured output (optional):** Have the agent (or a small parser) return `action_type` and summary so the webhook can log and optionally react (e.g. retry if escalate failed).
4. **Demo:** Prepare two E2E runs – OOM auto-fix and CreateContainerConfigError → JIRA + Slack – plus optional rollout-restart-only and liveness examples.

This keeps the workflow you have, adds clear boundaries between “agent fixes” and “agent escalates,” and gives you concrete demo scenarios and production improvements.
