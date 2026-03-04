"""
Kubernetes tools for the local test agent.

Uses default kubeconfig (~/.kube/config or KUBECONFIG) for Docker Desktop or any local cluster.
No EKS IAM; no proxy.
"""

import datetime
import json
import logging
import os
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from strands import tool

logger = logging.getLogger(__name__)


def _load_config() -> None:
    """Load kubeconfig or in-cluster config."""
    try:
        config.load_kube_config()
    except config.ConfigException:
        config.load_incluster_config()


def _get_core_v1() -> client.CoreV1Api:
    """Build CoreV1Api using local kubeconfig (e.g. Docker Desktop)."""
    _load_config()
    return client.CoreV1Api()


def _get_apps_v1() -> client.AppsV1Api:
    """Build AppsV1Api for Deployment/StatefulSet operations."""
    _load_config()
    return client.AppsV1Api()


# Strategic-merge PATCH: Kubernetes Python client does not accept _content_type;
# use call_api with Content-Type set so PATCH uses application/strategic-merge-patch+json.
def _patch_deployment_strategic(namespace: str, name: str, body: dict[str, Any]) -> None:
    api = _get_apps_v1()
    path = "/apis/apps/v1/namespaces/{namespace}/deployments/{name}"
    header_params = {
        "Accept": "application/json",
        "Content-Type": "application/strategic-merge-patch+json",
    }
    api.api_client.call_api(
        path,
        "PATCH",
        path_params={"namespace": namespace, "name": name},
        query_params=[],
        header_params=header_params,
        body=body,
        response_type="V1Deployment",
        auth_settings=["BearerToken"],
    )


def _patch_stateful_set_strategic(namespace: str, name: str, body: dict[str, Any]) -> None:
    api = _get_apps_v1()
    path = "/apis/apps/v1/namespaces/{namespace}/statefulsets/{name}"
    header_params = {
        "Accept": "application/json",
        "Content-Type": "application/strategic-merge-patch+json",
    }
    api.api_client.call_api(
        path,
        "PATCH",
        path_params={"namespace": namespace, "name": name},
        query_params=[],
        header_params=header_params,
        body=body,
        response_type="V1StatefulSet",
        auth_settings=["BearerToken"],
    )


def _patch_daemon_set_strategic(namespace: str, name: str, body: dict[str, Any]) -> None:
    api = _get_apps_v1()
    path = "/apis/apps/v1/namespaces/{namespace}/daemonsets/{name}"
    header_params = {
        "Accept": "application/json",
        "Content-Type": "application/strategic-merge-patch+json",
    }
    api.api_client.call_api(
        path,
        "PATCH",
        path_params={"namespace": namespace, "name": name},
        query_params=[],
        header_params=header_params,
        body=body,
        response_type="V1DaemonSet",
        auth_settings=["BearerToken"],
    )


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
        owner_refs = []
        for ref in (pod.metadata.owner_references or []):
            owner_refs.append({"kind": ref.kind, "name": ref.name})
        out = {
            "name": pod.metadata.name,
            "namespace": pod.metadata.namespace,
            "phase": status.phase,
            "reason": getattr(status, "reason") or "",
            "message": getattr(status, "message") or "",
            "owner_references": owner_refs,
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


def _get_max_memory_mb() -> int:
    """Max memory limit (MB) for auto-fix; avoid setting unsafe limits."""
    val = os.environ.get("K8S_MAX_MEMORY_LIMIT_MB", "2048")
    try:
        return max(64, min(8192, int(val)))
    except ValueError:
        return 2048


@tool
def k8s_get_deployment(namespace: str, deployment_name: str) -> str:
    """Get a Deployment spec: containers, image, resources (limits/requests). Use the deployment name from the pod's owner_references (describe_pod) or infer from pod name (e.g. pod 'demo-abc123' -> deployment 'demo')."""
    try:
        _safe_namespace(namespace)
        _safe_name(deployment_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    try:
        api = _get_apps_v1()
        dep = api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        containers = []
        for c in dep.spec.template.spec.containers or []:
            limits = {}
            requests = {}
            if c.resources and c.resources.limits:
                limits = {k: str(v) for k, v in c.resources.limits.items()}
            if c.resources and c.resources.requests:
                requests = {k: str(v) for k, v in c.resources.requests.items()}
            containers.append({
                "name": c.name,
                "image": c.image,
                "resources_limits": limits,
                "resources_requests": requests,
            })
        out = {
            "name": dep.metadata.name,
            "namespace": dep.metadata.namespace,
            "containers": containers,
        }
        return json.dumps(out, indent=2)
    except ApiException as e:
        logger.warning("get_deployment ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("get_deployment")
        return json.dumps({"error": str(e)})


@tool
def k8s_patch_deployment_resources(
    namespace: str,
    deployment_name: str,
    container_name: str,
    memory_limit: str,
    memory_request: str = "",
) -> str:
    """Patch a Deployment's container memory limit and optionally request. Use for OOMKilled: set memory_limit to max(2 × current limit, 256Mi) in Mi (e.g. '256Mi', '512Mi'). memory_request is optional; if empty, set to same as memory_limit. Values are capped at K8S_MAX_MEMORY_LIMIT_MB (default 2048MB)."""
    try:
        _safe_namespace(namespace)
        _safe_name(deployment_name)
        _safe_name(container_name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    max_mb = _get_max_memory_mb()
    if not memory_limit or not isinstance(memory_limit, str):
        return json.dumps({"error": "memory_limit must be a string (e.g. '256Mi')"})
    mem = memory_limit.strip()
    if not mem.endswith("Mi") and not mem.endswith("Gi"):
        return json.dumps({"error": "memory_limit must end with Mi or Gi (e.g. '512Mi')"})
    try:
        num = int(mem[:-2])
        if mem.endswith("Gi"):
            num_mb = num * 1024
        else:
            num_mb = num
        if num_mb > max_mb:
            num_mb = max_mb
            mem = f"{num_mb}Mi"
    except ValueError:
        return json.dumps({"error": f"Invalid memory format: {mem}"})
    req = (memory_request or "").strip() or mem
    try:
        api = _get_apps_v1()
        patch = {
            "spec": {
                "template": {
                    "spec": {
                        "containers": [
                            {
                                "name": container_name,
                                "resources": {
                                    "limits": {"memory": mem},
                                    "requests": {"memory": req},
                                },
                            }
                        ]
                    }
                }
            }
        }
        _patch_deployment_strategic(namespace, deployment_name, patch)
        return json.dumps({"ok": True, "message": f"Patched {container_name}: limits.memory={mem}, requests.memory={req}"})
    except ApiException as e:
        logger.warning("patch_deployment_resources ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("patch_deployment_resources")
        return json.dumps({"error": str(e)})


@tool
def k8s_rollout_restart(namespace: str, kind: str, name: str) -> str:
    """Restart a workload (rollout restart). kind must be 'deployment', 'statefulset', or 'daemonset'; name is the workload name. Use after patching resources or to clear transient failures. Call this at most once per workload per alert—do not retry if it succeeds or returns an error."""
    try:
        _safe_namespace(namespace)
        _safe_name(name)
    except ValueError as e:
        return json.dumps({"error": str(e)})
    k = (kind or "").strip().lower()
    if k not in ("deployment", "statefulset", "daemonset"):
        return json.dumps({"error": "kind must be 'deployment', 'statefulset', or 'daemonset'"})
    try:
        restarted_at = datetime.datetime.utcnow().isoformat() + "Z"
        body = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": restarted_at}}}}}
        if k == "deployment":
            _patch_deployment_strategic(namespace, name, body)
        elif k == "statefulset":
            _patch_stateful_set_strategic(namespace, name, body)
        else:
            _patch_daemon_set_strategic(namespace, name, body)
        return json.dumps({"ok": True, "message": f"Rollout restart triggered for {k}/{name}"})
    except ApiException as e:
        logger.warning("rollout_restart ApiException: %s", e)
        return json.dumps({"error": e.reason or str(e)})
    except Exception as e:
        logger.exception("rollout_restart")
        return json.dumps({"error": str(e)})
