#!/usr/bin/env python3
"""
Send a test Alertmanager-style webhook for the oom-demo pod (CrashLoopBackOff / OOMKilled).
Use after: kubectl apply -f oom-deployment.yaml

Either pass pod name as first arg, or we try to discover it from the cluster.
Webhook URL defaults to http://localhost:8080/webhook (set WEBHOOK_URL to override).
"""

import os
import sys

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
except ImportError:
    config = client = ApiException = None


def get_oom_demo_pod_name(namespace: str = "default") -> str:
    if client is None:
        return ""
    try:
        config.load_kube_config()
    except Exception:
        try:
            config.load_incluster_config()
        except Exception:
            return ""
    api = client.CoreV1Api()
    try:
        resp = api.list_namespaced_pod(
            namespace=namespace,
            label_selector="app=oom-demo",
        )
        if resp.items:
            return resp.items[0].metadata.name
    except ApiException:
        pass
    return ""


def main() -> None:
    pod_name = (sys.argv[1].strip() if len(sys.argv) > 1 else "") or get_oom_demo_pod_name()
    if not pod_name:
        print("Usage: python send_test_webhook_oom.py [pod-name]", file=sys.stderr)
        print("  Or run after: kubectl apply -f oom-deployment.yaml (script will discover pod)", file=sys.stderr)
        sys.exit(1)

    url = os.environ.get("WEBHOOK_URL", "http://localhost:8080/webhook")
    payload = {
        "status": "firing",
        "groupLabels": {"alertname": "PodCrashLoopBackOffCritical"},
        "commonLabels": {
            "alertname": "PodCrashLoopBackOffCritical",
            "severity": "critical",
            "namespace": "default",
            "pod": pod_name,
        },
        "alerts": [
            {
                "status": "firing",
                "labels": {
                    "alertname": "PodCrashLoopBackOffCritical",
                    "severity": "critical",
                    "namespace": "default",
                    "pod": pod_name,
                },
                "annotations": {
                    "summary": "Pod in CrashLoopBackOff (OOMKilled)",
                    "description": f"Pod default/{pod_name} is in CrashLoopBackOff (critical).",
                },
            }
        ],
    }

    import requests
    try:
        r = requests.post(url, json=payload, timeout=30)
        print("Status:", r.status_code)
        print("Response:", r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)
    except requests.RequestException as e:
        print("Request failed:", e, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
