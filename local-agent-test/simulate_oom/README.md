# Simulate OOMKilled → Critical Alert → Webhook → Agent Auto-Fix

Deploy a pod that gets **OOMKilled**, so Prometheus fires a **critical** alert and Alertmanager sends it to your webhook. The agent can then auto-fix by increasing the deployment memory and doing a rollout restart.

## 1. Deploy the OOM deployment

```bash
kubectl apply -f oom-deployment.yaml
```

Within a few seconds the pod will start, allocate ~64Mi (over the 32Mi limit), get OOMKilled, and enter **CrashLoopBackOff**.

Verify:

```bash
kubectl get pods -l app=oom-demo
kubectl describe pod -l app=oom-demo
# Last State: Terminated, Reason: OOMKilled, Exit Code: 137
kubectl get events -n default --field-selector involvedObject.name=<pod-name>
# Reason: OOMKilled
```

## 2. Ensure Prometheus fires a critical alert

Your Prometheus must have an alert rule that fires when a pod is in CrashLoopBackOff and sets **severity=critical**, and the alert must include **namespace** and **pod** in the labels (so the webhook payload has them for the agent).

- If you already have a rule like **KubePodCrashLooping** (or similar) with `severity: critical` and labels `namespace`, `pod`, you can skip this step.
- Otherwise, add the provided rule in the **monitoring** namespace (where kube-prometheus-stack runs):

```bash
kubectl apply -f prometheus-rule-oom-critical.yaml
```

The rule uses **namespace: monitoring** and **release: prometheus-stack** so Prometheus picks it up. If you used a different Helm release name, edit `metadata.labels.release` in the YAML to match (e.g. same as your other `PrometheusRule` resources in monitoring).

After the rule is active, wait **at least 1 minute** (`for: 1m`) after the pod is in CrashLoopBackOff. Then Alertmanager will send the alert to the **agent-webhook** receiver.

### Alert not firing / webhook not receiving?

1. **Apply the rule** (if you haven’t): `kubectl apply -f prometheus-rule-oom-critical.yaml`
2. **Rule labels must match** your Helm release: the rule uses `release: prometheus-stack`. If you installed with a different release name, fix the label and re-apply.
3. **Check Prometheus has the rule**: Prometheus UI → Status → Rules (or Alerts). You should see `PodCrashLoopBackOffCritical`.
4. **Check the metric exists**: In Prometheus, run `kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}`. If you get no result, kube-state-metrics may not be running or not exposing this metric.
5. **Wait 1 minute** after the pod enters CrashLoopBackOff before the alert fires.
6. **Alertmanager route**: Your config must route `severity="critical"` to the agent-webhook receiver (see `monitoring/alertmanager-secret.yaml`).

## 3. Run the webhook server and trigger the flow

1. Start the webhook server (from `local-agent-test`):

   ```bash
   cd local-agent-test
   python webhook_server.py
   ```

2. Alertmanager will POST to `http://host.docker.internal:8080/webhook` (or your configured URL) when the critical alert fires. No manual curl needed if Alertmanager is already configured.

3. The agent will:
   - Use **namespace** and **pod** from the alert
   - Call `k8s_describe_pod`, `k8s_get_events`, etc., see **OOMKilled**
   - Resolve the owning **Deployment** from `owner_references` (e.g. `oom-demo`)
   - Call **k8s_get_deployment** → **k8s_patch_deployment_resources** (e.g. increase to 256Mi) → **k8s_rollout_restart**
   - Respond with “Auto-fixed: …”

## 4. Optional: send a test webhook by hand

If you want to simulate the alert without waiting for Prometheus/Alertmanager:

```bash
cd local-agent-test
python -c "
import requests, json
payload = {
    'status': 'firing',
    'alerts': [{
        'status': 'firing',
        'labels': {'alertname': 'PodCrashLoopBackOffCritical', 'severity': 'critical', 'namespace': 'default', 'pod': ''},
        'annotations': {'summary': 'Pod in CrashLoopBackOff'}
    }]
}
# Fill pod name from: kubectl get pods -l app=oom-demo -o jsonpath='{.items[0].metadata.name}'
payload['alerts'][0]['labels']['pod'] = 'oom-demo-xxxxx'   # replace xxxxx with actual suffix
r = requests.post('http://localhost:8080/webhook', json=payload)
print(r.status_code, r.json())
"
```

Replace `oom-demo-xxxxx` with the actual pod name from `kubectl get pods -l app=oom-demo`.

## 5. Clean up

```bash
kubectl delete -f oom-deployment.yaml
# If you added the PrometheusRule (it lives in monitoring namespace):
kubectl delete -f prometheus-rule-oom-critical.yaml
```
