# Webhook server: receives Alertmanager webhooks and runs the agent (local Strands or, later, invokes AgentCore).
# Build from repo root: docker build -f webhook-server/Dockerfile .
# The app code lives in local-agent-test/; we copy it here to keep a single source of truth.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies from local-agent-test
COPY local-agent-test/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code. .dockerignore at repo root excludes .venv, .env, __pycache__ from local-agent-test
COPY local-agent-test/ .

EXPOSE 8080

# Run the webhook server (listens on 0.0.0.0:8080)
CMD ["python", "-m", "uvicorn", "webhook_server:app", "--host", "0.0.0.0", "--port", "8080"]
