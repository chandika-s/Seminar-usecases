# Kubernetes Manifests for Alertmanager AgentCore Bridge

Use a **Deployment with multiple replicas** (default: 2) for:

- **High availability** – another pod serves webhooks if one fails
- **Rolling updates** – no downtime when you change the image or config
- **No single point of failure** – Alertmanager can retry, but replicas reduce dropped alerts

A single Pod is not recommended for a webhook receiver that must be always on.

## Prerequisites

1. **Image**: Build and push the bridge image to a registry (e.g. ECR):

   ```bash
   docker build -t 123456789012.dkr.ecr.us-east-1.amazonaws.com/alertmanager-agentcore-bridge:latest .
   docker push 123456789012.dkr.ecr.us-east-1.amazonaws.com/alertmanager-agentcore-bridge:latest
   ```

2. **IAM / EKS authentication**: The bridge calls the AWS API `InvokeAgentRuntime`; that API uses **normal AWS IAM (SigV4)**. AgentCore does **not** require a separate OIDC login or special auth—it just needs the pod to have AWS credentials that have `bedrock-agentcore:InvokeAgentRuntime` permission.

   On EKS, the standard way to give the pod those credentials is **IRSA (IAM Roles for Service Accounts)**, which uses the cluster’s **OIDC provider** so the pod can *assume* an IAM role. So you need **both**:
   - An **IAM role** with a policy allowing `bedrock-agentcore:InvokeAgentRuntime` (see `iam-policy-example.json`).
   - That role’s **trust policy** allowing your EKS cluster OIDC provider to assume it (so the pod can get credentials via OIDC).
   - The **role ARN** set on the ServiceAccount (e.g. `eks.amazonaws.com/role-arn`) so pods using this ServiceAccount receive that role’s credentials.

   In short: **the role ARN is enough for permissions**; on EKS that role is **assumed via OIDC (IRSA)**. You don’t configure “OIDC auth” for AgentCore itself—you use IRSA so the pod has an IAM role, and that role is what AgentCore sees.

   **Creating the IRSA role (EKS):** Create an IAM policy from `iam-policy-example.json` (replace REGION/ACCOUNT_ID/AGENT_RUNTIME_ID), then create a role trustable by your cluster’s OIDC provider and attach the policy. Easiest with `eksctl`:
   ```bash
   eksctl create iamserviceaccount --name alertmanager-agentcore-bridge \
     --namespace alertmanager-agentcore-bridge --cluster <cluster-name> \
     --attach-policy-arn arn:aws:iam::ACCOUNT:policy/YourBedrockAgentCoreInvokePolicy --approve
   ```
   This creates the IAM role (with OIDC trust), the policy attachment, and annotates the ServiceAccount. No need to annotate `serviceaccount.yaml` by hand if you use this.

3. **Secret**: Create the secret with your real values **before** applying the Deployment. Either:
   - Edit `secret.yaml` and replace `REPLACE_WITH_YOUR_AGENT_RUNTIME_ARN` (then `kubectl apply -f secret.yaml`), or
   - Create the secret manually and skip applying `secret.yaml`:
     ```bash
     kubectl create secret generic alertmanager-agentcore-bridge-secret \
       --namespace alertmanager-agentcore-bridge \
       --from-literal=AGENT_RUNTIME_ARN='arn:aws:bedrock-agentcore:us-east-1:123456789012:agent-runtime/xxx' \
       --from-literal=WEBHOOK_SECRET='optional-secret'
     ```

## Apply order

```bash
kubectl apply -f namespace.yaml
kubectl apply -f configmap.yaml
kubectl apply -f secret.yaml      # after editing or creating the secret
kubectl apply -f serviceaccount.yaml
kubectl apply -f deployment.yaml
kubectl apply -f service.yaml
```

Or apply the whole directory (ensure secret is created/updated first):

```bash
kubectl apply -f k8s/
```

## Configure Deployment image

Set the correct image in `deployment.yaml`:

```yaml
containers:
  - name: bridge
    image: <your-registry>/alertmanager-agentcore-bridge:<tag>
```

## Alertmanager webhook URL

From the same cluster:

- **Same namespace**: `http://alertmanager-agentcore-bridge:8080/webhook`
- **Other namespace**: `http://alertmanager-agentcore-bridge.alertmanager-agentcore-bridge.svc.cluster.local:8080/webhook`

Use this URL in your Alertmanager `webhook_configs[].url`.

## Optional: HPA

For higher alert volume you can add a HorizontalPodAutoscaler (not included) to scale the Deployment based on CPU or custom metrics.
