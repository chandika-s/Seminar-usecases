"""
Local Kubernetes agent (Strands) for testing with Docker Desktop K8s.

Investigates alerts (list pods, logs, describe, events), then either:
- Auto-fixes when safe (e.g. OOMKilled: patch deployment memory + rollout restart).
- Escalates when not (create JIRA ticket + Slack notification).

Uses OpenAI; load OPENAI_API_KEY from .env. No Bedrock required.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent
from strands.models.openai import OpenAIModel

from k8s_tools import (
    k8s_list_pods,
    k8s_get_logs,
    k8s_describe_pod,
    k8s_get_events,
    k8s_get_deployment,
    k8s_patch_deployment_resources,
    k8s_rollout_restart,
)
from escalation_tools import create_jira_ticket, send_slack_notification

# Load .env from this directory (or parent) so OPENAI_API_KEY can be set there
load_dotenv(Path(__file__).resolve().parent / ".env")
api_key = os.environ.get("OPENAI_API_KEY", "")
openai_model_id = os.environ.get("OPENAI_MODEL_ID", "gpt-4o-mini")

model = OpenAIModel(
    client_args={"api_key": api_key},
    model_id=openai_model_id,
    params={"max_tokens": 2000, "temperature": 0.2},
)

SYSTEM_PROMPT = """You are a Kubernetes troubleshooting agent. When you receive an Alertmanager webhook:

0. If the alert's namespace (from labels) is kube-system or monitoring: do not call any tools. Respond immediately with "Ignored: kube-system/monitoring namespace. No action taken." Then stop. Do not investigate or remediate kube-system or monitoring (stack components).

1. Use the namespace and pod from the alert (labels: namespace, pod) to investigate: call k8s_list_pods, k8s_get_logs, k8s_describe_pod, and k8s_get_events. Use the exact namespace and pod names from the alert; default namespace is 'default'.

2. Identify root cause from logs, pod status (reason, container statuses), and events (e.g. OOMKilled, Failed, BackOff, CreateContainerConfigError).

3. Decide and act—do each remediation at most once. Do not retry the same fix. If a tool returns an error (e.g. "kind must be deployment/statefulset/daemonset", "Not Found") or the fix does not apply, stop attempting that fix and either escalate or conclude with a short summary so you can finish and not block other alerts.
   - AUTO-FIX (do it once): When the fix is safe and deterministic:
     a) OOMKilled and owner is Deployment: Get deployment from owner_references. Call k8s_get_deployment to read current resources_limits.memory (e.g. 32Mi). If current limit is already >= 512Mi, do not patch again—escalate (create_jira_ticket, send_slack_notification) and say "Memory already >= 512Mi; previous increase did not resolve OOM. Human review needed." Otherwise compute new_mb = max(2 × current_limit_in_Mi, 256); if current is in Gi, convert to Mi first. Cap at 2048 (K8S_MAX_MEMORY_LIMIT_MB). Call k8s_patch_deployment_resources with memory_limit = str(new_mb) + 'Mi', then k8s_rollout_restart(namespace, 'deployment', name). Do not retry if any step fails.
     b) Transient restarts (no clear config error) and owner is Deployment/StatefulSet/DaemonSet: Call k8s_rollout_restart once with the correct kind ('deployment', 'statefulset', or 'daemonset'). If the tool returns an error, do not call it again—conclude or escalate.
   - ESCALATE (do it once): When you cannot safely fix (e.g. CreateContainerConfigError, missing Secret/env, ImagePullBackOff due to auth, or workload type not supported for auto-fix): Call create_jira_ticket once, then send_slack_notification once. Always pass the namespace, pod, and alertname from the alert labels to both tools so we avoid re-triggering on the same issue. Then give your final response and stop.

4. After one attempt at auto-fix or escalation, provide your final response and stop. Do not retry the same rollout_restart, patch, or escalation calls. State clearly: "Auto-fixed: ..." or "Escalated: ..." or "Could not auto-fix: <reason>. Escalated / No further action."."""

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[
        k8s_list_pods,
        k8s_get_logs,
        k8s_describe_pod,
        k8s_get_events,
        k8s_get_deployment,
        k8s_patch_deployment_resources,
        k8s_rollout_restart,
        create_jira_ticket,
        send_slack_notification,
    ],
)


def run(prompt: str):
    """Run the agent with the given prompt and print the response."""
    response = agent(prompt)
    return response


if __name__ == "__main__":
    import sys
    if not api_key:
        print("Error: Set OPENAI_API_KEY in .env or in the environment.")
        sys.exit(1)
    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
    else:
        user_input = "List pods in the default namespace."
    print("Prompt:", user_input)
    print("-" * 40)
    result = run(user_input)
    print(result)
