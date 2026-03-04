"""
Local Kubernetes agent (Strands) for testing with Docker Desktop K8s.

Uses default kubeconfig (~/.kube/config). Give the agent a prompt with pod name,
namespace, etc., and it will use the tools to list pods and get logs.
Uses OpenAI; load OPENAI_API_KEY from .env or environment. No Bedrock required.
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
)

# Load .env from this directory (or parent) so OPENAI_API_KEY can be set there
load_dotenv(Path(__file__).resolve().parent / ".env")
api_key = os.environ.get("OPENAI_API_KEY", "")
openai_model_id = os.environ.get("OPENAI_MODEL_ID", "gpt-4o-mini")

model = OpenAIModel(
    client_args={"api_key": api_key},
    model_id=openai_model_id,
    params={"max_tokens": 2000, "temperature": 0.2},
)

SYSTEM_PROMPT = """You are a Kubernetes troubleshooting agent. When you receive an Alertmanager webhook (CrashLoopBackOff or similar):

1. Use the namespace and pod from the alert (labels: namespace, pod) to call k8s_list_pods, k8s_get_logs, k8s_describe_pod, and k8s_get_events.
2. Identify root cause from logs, pod status, and events.
3. Recommend a fix (e.g. delete pod, restart deployment, fix image or command). Do not execute any changes; only recommend.

Use the exact namespace and pod names from the alert. Default namespace is 'default'."""

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[
        k8s_list_pods,
        k8s_get_logs,
        k8s_describe_pod,
        k8s_get_events,
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
