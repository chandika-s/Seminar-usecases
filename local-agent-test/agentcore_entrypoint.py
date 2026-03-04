"""
AgentCore Runtime entrypoint: same workflow (investigate → email → incident → approve → apply)
wrapped for Bedrock AgentCore. Deploy this file as the entrypoint; the bridge invokes it with
payload containing "prompt" and "alertmanager_payload".

For local-agent-test this entrypoint uses the same agent (OpenAI + local kubeconfig). For production
AgentCore deployment you would switch to BedrockModel and EKS IAM auth (reuse tools from
agentic-k8s-troubleshooter/agent) and set EMAIL_USE_SES=true, INCIDENT_REPORT_WEBHOOK_URL, etc.
"""

import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from agent import agent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = BedrockAgentCoreApp()


def _build_initial_message(payload: dict) -> str:
    """Use prompt from bridge payload (bridge already builds it from alertmanager_payload)."""
    return payload.get("prompt", "") or "No prompt provided."


@app.entrypoint
async def k8s_troubleshooter(payload: dict, context) -> str:
    """Entrypoint for AgentCore: run the agent with the bridge payload."""
    user_input = _build_initial_message(payload)
    logger.info("Running agent for alert (prompt length=%s)", len(user_input))
    return agent(user_input)


if __name__ == "__main__":
    app.run()
