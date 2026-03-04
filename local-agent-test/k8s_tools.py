"""
Kubernetes tools for the local test agent.

Uses default kubeconfig (~/.kube/config or KUBECONFIG) for Docker Desktop or any local cluster.
No EKS IAM; no proxy.
"""

import json
import logging
import os
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from strands import tool

logger = logging.getLogger(__name__)


def _get_core_v1() -> client.CoreV1Api:
    """Build CoreV1Api using local kubeconfig (e.g. Docker Desktop)."""
    try:
        config.load_kube_config()
    except config.ConfigException:
        config.load_incluster_config()
    return client.CoreV1Api()


def _safe_namespace(ns: str) -> str:
    if not ns or "/" in ns or ".." in ns:
        raise ValueError("Invalid namespace")
    return ns


def _safe_name(name: str) -> str:
    if not name or "/" in name or ".." in name:
        raise ValueError("Invalid name")
    return name


@tool
def k8s_list_pods(namespace: str = "default", label_selector: str = "") -> str:
    """List pods in a Kubernetes namespace. Default namespace is 'default'. Use label_selector to filter (e.g. app=myapp)."""
    try:
        _safe_namespace(namespace)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    try:
        api = _get_core_v1()
        resp = api.list_namespaced_pod(namespace=namespace, label_selector=label_selector or None)
        items = []
        for p in resp.items:
            items.append({
                "name": p.metadata.name,
                "phase": p.status.phase,
                "reason": getattr(p.status, "reason") or "",
                "message": getattr(p.status, "message") or "",
                "restart_count": sum(c.restart_count for c in (p.status.container_statuses or [])),
            })
        return json.dumps({"pods": items}, indent=2)
    except ApiException as e:
        logger.warning("list_pods ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("list_pods")
        return json.dumps({"error": str(e)})


@tool
def k8s_get_logs(namespace: str, pod_name: str, tail_lines: int = 100) -> str:
    """Get recent logs for a pod. Give namespace and pod_name. Use tail_lines to limit lines (max 500)."""
    try:
        _safe_namespace(namespace)
        _safe_name(pod_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    if tail_lines > 500:
        tail_lines = 500
    try:
        api = _get_core_v1()
        resp = api.read_namespaced_pod_log(
            namespace=namespace,
            name=pod_name,
            tail_lines=tail_lines,
        )
        return resp if isinstance(resp, str) else json.dumps(resp)
    except ApiException as e:
        logger.warning("get_logs ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("get_logs")
        return json.dumps({"error": str(e)})


@tool
def k8s_describe_pod(namespace: str, pod_name: str) -> str:
    """Get pod description: phase, reason, message, container statuses. Give namespace and pod_name."""
    try:
        _safe_namespace(namespace)
        _safe_name(pod_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    try:
        api = _get_core_v1()
        pod = api.read_namespaced_pod(name=pod_name, namespace=namespace)
        status = pod.status
        out = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": status.phase,
            "reason": getattr(status, "reason") or "",
            "message": getattr(status, "message") or "",
            "container_statuses": [
                {"name": cs.name, "ready": cs.ready, "restart_count": cs.restart_count}
                for cs in (status.container_statuses or [])
            ],
        }
        return json.dumps(out, indent=2)
    except ApiException as e:
        logger.warning("describe_pod ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("describe_pod")
        return json.dumps({"error": str(e)})


@tool
def k8s_get_events(namespace: str) -> str:
    """Get recent events in a namespace (e.g. Failed, BackOff, OOMKilled). Use this to diagnose CrashLoopBackOff."""
    try:
        _safe_namespace(namespace)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    try:
        api = _get_core_v1()
        resp = api.list_namespaced_event(namespace=namespace, limit=50)
        events = []
        for e in resp.items:
            events.append({
                "reason": e.reason,
                "type": e.type,
                "message": e.message,
                "involved_object": f"{e.involved_object.kind}/{e.involved_object.name}" if e.involved_object else "",
                "last_timestamp": str(e.last_timestamp) if e.last_timestamp else "",
            })
        return json.dumps({"events": events}, indent=2)
    except ApiException as e:
        logger.warning("get_events ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("get_events")
        return json.dumps({"error": str(e)})
