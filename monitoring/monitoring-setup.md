# Monitoring EKS with Prometheus and Grafana

This guide covers the steps to deploy Prometheus and Grafana on an EKS cluster to monitor pod health and OOM (Out Of Memory) kills using the `kube-prometheus-stack` Helm chart.

## Prerequisites
- **kubectl**: Configured to access your EKS cluster.
- **Helm**: Installed on your local machine.

## Step 1: Add Helm Repository
```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
```

## Step 2: Create Monitoring Namespace
```bash
kubectl create namespace monitoring
```

## Step 3: Install Kube-Prometheus Stack
This chart installs Prometheus, Grafana, Alertmanager, and optionally Node Exporter.
```bash
helm install prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false \
  --set prometheus-node-exporter.enabled=false
```
*Note: Default Grafana password is set to `admin`. Change this for production environments.*

**Node Exporter disabled:** `prometheus-node-exporter.enabled=false` is set because the node-exporter DaemonSet often enters CrashLoopBackOff on local clusters (e.g. Docker Desktop Kubernetes) due to host path or permission issues. For local/demo use, Prometheus and Alertmanager are sufficient. Re-enable it (remove the `--set prometheus-node-exporter.enabled=false` line) if you need node metrics on a production cluster.

## Step 4: Verify Deployment
```bash
kubectl get pods -n monitoring
```

### Disable node-exporter on an existing install
If the stack is already installed and the node-exporter pod is in CrashLoopBackOff (e.g. on Docker Desktop), you can either upgrade via Helm or remove the DaemonSet manually.

**Option A – Helm upgrade** (disables node-exporter in Helm state):
```bash
helm upgrade prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --reuse-values \
  --set prometheus-node-exporter.enabled=false
```
*If you see a conflict on the Alertmanager Secret (e.g. you applied a custom `alertmanager-secret.yaml`), Helm may fail. Use Option B to remove the DaemonSet only, or run the upgrade with `--force` (Helm will overwrite the secret; re-apply your custom Alertmanager config afterward if needed).*

**Option B – Remove the DaemonSet only** (stops CrashLoopBackOff without changing Helm values):
```bash
kubectl delete daemonset prometheus-stack-prometheus-node-exporter -n monitoring
```

## Step 5: Access Grafana Dashboard
Use port-forwarding to access the Grafana UI locally:
```bash
kubectl port-forward deployment/prometheus-stack-grafana 3000:3000 -n monitoring
```
Then open **[http://localhost:3000](http://localhost:3000)** in your browser.
- **Username**: `admin`
- **Password**: `admin`

## Step 6: Monitoring OOM Kills
Prometheus is pre-configured as the data source. To specifically monitor OOM kills:

### Built-in Dashboards
1. Navigate to **Dashboards > Browse**.
2. Select **Kubernetes / Compute Resources / Pod**.

### Custom PromQL Query for OOM Kills
Create a new panel with this query to detect terminated containers due to memory limits:
```promql
kube_pod_container_status_terminated_reason{reason="OOMKilled"}
```

## Step 7: Setting up Alerts
To receive notifications for OOM kills, create an alert rule with:
```promql
sum by (pod, namespace) (kube_pod_container_status_terminated_reason{reason="OOMKilled"}) > 0
```
Set the evaluation interval to `1m`.
