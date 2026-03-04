# Webhook Server (Docker / EKS)

HTTP server that receives **Alertmanager webhooks** and runs the troubleshooting agent. Intended to run as a **container on EKS** (or any Kubernetes cluster) so Alertmanager in the cluster can reach it.

The application code lives in **`../local-agent-test/`**; this directory contains only the **container build** and **Kubernetes manifests** to keep the repo clean.

## Build

Build from the **repository root** (so `local-agent-test/` can be copied into the image):

```bash
# From repo root
docker build -f webhook-server/Dockerfile -t alertmanager-webhook-server:latest .
```

Optional: tag for a registry:

```bash
docker tag alertmanager-webhook-server:latest <account>.dkr.ecr.<region>.amazonaws.com/alertmanager-webhook-server:latest
docker push <account>.dkr.ecr.<region>.amazonaws.com/alertmanager-webhook-server:latest
```

## Run locally (container)

```bash
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="$OPENAI_API_KEY" \
  -e KUBECONFIG=/path/to/kubeconfig \
  -v "$HOME/.kube:/root/.kube:ro" \
  alertmanager-webhook-server:latest
```

For EKS, the pod typically uses an IAM role (IRSA) and in-cluster kubeconfig; no host kubeconfig mount.

## Deploy on EKS

1. Build and push the image to ECR (or your registry).
2. Create a namespace and any secrets (e.g. `OPENAI_API_KEY`, `JIRA_*`, `SLACK_WEBHOOK_URL`).
3. Apply the deployment and service:

   ```bash
   kubectl apply -f webhook-server/k8s-deployment.yaml
   ```

4. Expose the service (LoadBalancer, Ingress, or ClusterIP and point Alertmanager to the service URL).
5. In Alertmanager config, set the webhook URL to `http://<service>.<namespace>.svc.cluster.local:8080/webhook` (or the external URL if you use an Ingress).

## Environment variables

Same as `local-agent-test/` (see `.env.example` there):

- **OPENAI_API_KEY** – required for the Strands agent.
- **KUBECONFIG** – optional in-cluster; omit when running in K8s so the pod uses the in-cluster config.
- **JIRA_***, **SLACK_WEBHOOK_URL** – optional, for escalation.
- **ESCALATION_STORE_TTL_HOURS** – optional, default 24.

Secrets should be provided via Kubernetes Secrets or External Secrets; do not bake them into the image.
