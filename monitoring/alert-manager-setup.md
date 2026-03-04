Install kube-promethus stack
```
helm install prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --set grafana.adminPassword=admin \
  --set prometheus.prometheusSpec.podMonitorSelectorNilUsesHelmValues=false \
  --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
```

Ensured Alertmanager Exists and Is Reachable
```
kubectl -n monitoring get svc | grep alertmanager
kubectl -n monitoring get endpoints | grep alertmanager
```

port-forward
```
kubectl -n monitoring port-forward svc/prometheus-stack-kube-prom-alertmanager 9093:9093
```

http://localhost:9093/#/alerts

**Check which host is reachable from Alertmanager (for webhook URL):**  
Run this one-liner to test `localhost:8080` and `host.docker.internal:8080` from inside the Alertmanager container. Use the host that shows REACHABLE (or any HTTP response like 404) in your `agent-webhook` URL.
```bash
kubectl -n monitoring exec $(kubectl -n monitoring get pod -l app.kubernetes.io/name=alertmanager -o jsonpath='{.items[0].metadata.name}') -c alertmanager -- sh -c 'for h in localhost host.docker.internal; do echo -n "$h:8080 => "; e=$(wget -q -O /dev/null --timeout=2 "http://$h:8080/" 2>&1); echo "$e" | grep -qE "refused|returned error|saved" && echo "REACHABLE" || (echo "$e" | grep -qE "timed|resolve|not known" && echo "NOT REACHABLE" || echo "$e"); done'
```
Interpretation: **REACHABLE** = host reached (connection refused or HTTP response). **NOT REACHABLE** = timeout or name not resolved.

**Check if Alertmanager sent alerts to webhook (and see the error):**  
If you see `AlertmanagerFailedToSendAlerts` with `reason="clientError"` in the UI, Alertmanager *is* sending to the webhook but the receiver returned 4xx. Use this to see the exact error (e.g. 404, path wrong):
```bash
kubectl -n monitoring logs -l app.kubernetes.io/name=alertmanager -c alertmanager --tail=200 | grep -E "Notify for alerts failed|webhook|dispatch"
```
Look for `unexpected status code 404` (wrong path), `connection refused` (nothing on that port), or `timed out` (host unreachable). Fix the webhook URL or ensure the webhook server exposes the path and returns 2xx for POST.

Created Custom Prometheus Alert Rules:

Created a PrometheusRule resource to monitor application failures such as:
	•	CrashLoopBackOff
	•	OOMKilled
	•	NotReady pods
	•	ImagePullBackOff
	•	CreateContainerConfigError

demo-app-alerts.yaml
```
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: demo-app-failure-alerts
  namespace: monitoring
  labels:
    release: prometheus-stack   # IMPORTANT: must match your Helm release name
spec:
  groups:
  - name: demo-app.rules
    rules:
    - alert: DemoAppCrashLooping
      expr: |
        kube_pod_container_status_waiting_reason{namespace="default", pod=~"demo-app-.*", reason="CrashLoopBackOff"} == 1
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "demo-app is CrashLoopBackOff"
        description: "Pod {{ $labels.pod }} container {{ $labels.container }} is CrashLoopBackOff for >1m."

    - alert: DemoAppCreateContainerConfigError
      expr: |
        kube_pod_container_status_waiting_reason{namespace="default", pod=~"demo-app-.*", reason="CreateContainerConfigError"} == 1
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "demo-app CreateContainerConfigError"
        description: "Pod {{ $labels.pod }} cannot start due to config error (often missing Secret/ConfigMap)."

    - alert: DemoAppImagePullBackOff
      expr: |
        kube_pod_container_status_waiting_reason{namespace="default", pod=~"demo-app-.*", reason=~"ImagePullBackOff|ErrImagePull"} == 1
      for: 1m
      labels:
        severity: critical
      annotations:
        summary: "demo-app image pull failing"
        description: "Pod {{ $labels.pod }} has {{ $labels.reason }} for >1m."

    - alert: DemoAppNotReady
      expr: |
        kube_pod_status_ready{namespace="default", condition="true", pod=~"demo-app-.*"} == 0
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "demo-app pod not Ready"
        description: "Pod {{ $labels.pod }} has been NotReady for >2m (readiness probe failing or startup issues)."

    - alert: DemoAppOOMKilled
      expr: |
        kube_pod_container_status_last_terminated_reason{namespace="default", pod=~"demo-app-.*", reason="OOMKilled"} == 1
      for: 0m
      labels:
        severity: critical
      annotations:
        summary: "demo-app OOMKilled"
        description: "Pod {{ $labels.pod }} container {{ $labels.container }} was OOMKilled."
```

```
kubectl apply -f demo-app-alerts.yaml
```


Configured Alertmanager Email Receiver

```
alertmanager:
  config:
    global:
      smtp_smarthost: "smtp.gmail.com:587"
      smtp_from: "erchandika@gmail.com"
      smtp_auth_username: "erchandika@gmail.com"
      smtp_auth_password: "xxxxx"
      smtp_require_tls: true

    route:
      receiver: "null"
      routes:
        - matchers:
            - severity="critical"
          receiver: "email"

    receivers:
      - name: "null"

      - name: "email"
        email_configs:
          - to: "cr.crazylearning@gmail.com"
            send_resolved: true
```

helm upgrade prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring -f values-email.yaml


n8n webhook alert:

values-n8n.yaml
```
alertmanager:
  config:
    route:
      receiver: "email"   # keep your current default receiver (email)
      group_by: ["alertname", "namespace", "pod"]
      group_wait: 10s
      group_interval: 1m
      repeat_interval: 2h

      routes:
        # Send *critical* Kubernetes workload issues to n8n as well
        - matchers:
            - severity="critical"
          receiver: "n8n"
          continue: true   # ALSO send to default receiver (email) after n8n

        # Optionally: send specific alerts regardless of severity
        - matchers:
            - alertname=~"DemoAppCrashLooping|DemoAppOOMKilled|KubePodCrashLooping|KubePodNotReady"
          receiver: "n8n"
          continue: true

    receivers:
      # keep your existing receivers (email, null, etc.)
      - name: "n8n"
        webhook_configs:
          - url: "https://<YOUR-N8N-HOST>/webhook/alertmanager"
            send_resolved: true
            max_alerts: 0
```

```
helm upgrade prometheus-stack prometheus-community/kube-prometheus-stack \
  -n monitoring -f values-n8n.yaml
```
