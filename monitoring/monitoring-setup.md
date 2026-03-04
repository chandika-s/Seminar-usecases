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
This chart installs Prometheus, Grafana, Alertmanager, and Node Exporters.
```bash
helm install prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
```
*Note: Default Grafana password is set to `admin`. Change this for production environments.*

## Step 4: Verify Deployment
```bash
kubectl get pods -n monitoring
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
