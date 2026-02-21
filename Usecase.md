DevOps Use Cases Resolvable by Agentic AI
1) CrashLoopBackOff due to bad config / missing env
Why it’s common: config drift, wrong ConfigMap/Secret key, typo in env name, bad feature flag.
Alert trigger (typical)


kube_pod_container_status_restarts_total increasing fast


kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}


What the agent checks


kubectl describe pod → last termination exit code


kubectl logs --previous → errors like:


missing required env VAR_X


failed to load config file


panic: ...


Proposed fix


identify missing env / wrong key; point to the correct Secret/ConfigMap key


Auto-fix (safe)


If you have “known-good” config in Git/SSOT: patch the Deployment env var key or mount reference + rollout restart


Guardrails: only allow patching whitelisted env keys / only in non-prod for demo


2) CreateContainerConfigError: Secret/ConfigMap not found
Why it’s common: renamed secret, deleted secret, wrong namespace, Helm uninstall/reinstall, ExternalSecrets delayed.
Alert trigger


kube_pod_container_status_waiting_reason{reason="CreateContainerConfigError"}


What the agent checks


kubectl describe pod events show:


secret "X" not found


configmap "Y" not found


Proposed fix


“Create secret/configmap X in namespace N” or “Fix reference to correct name”


Auto-fix (very L1-friendly)


Recreate the missing Secret/ConfigMap from a template (for demo, store it in a safe internal repo / parameter store)


If ExternalSecrets is used: nudge by re-sync / annotate ExternalSecret (depending on your operator)


Guardrails: only recreate secrets from approved source; never print secret values in chat/logs


3) ImagePullBackOff: wrong image tag or missing registry credentials
Why it’s common: CI published different tag, typo in tag, rotated registry token, new namespace missing pull secret.
Alert trigger


kube_pod_container_status_waiting_reason{reason=~"ErrImagePull|ImagePullBackOff"}


What the agent checks


kubectl describe pod events like:


manifest unknown


pull access denied


toomanyrequests


Proposed fix


If manifest unknown: correct image tag (use last successful build tag)


If pull access denied: add imagePullSecrets / fix secret


Auto-fix


Patch Deployment to last-known-good image tag (from your deployment history / GitOps)


Create/attach imagePullSecret from approved credentials store


Guardrails: only rollback within same repo/app; require approval in prod


4) Readiness probe failing: pod Running but not receiving traffic
Why it’s common: wrong probe path/port after app change, slower startup, dependency check too strict, misconfigured service port.
Alert trigger


Service errors / 5xx increase (via ingress metrics) while pods look “up”


kube_pod_status_ready{condition="true"} drops, or not ready endpoints


What the agent checks


kubectl describe pod shows Readiness probe failed: HTTP 404/500 or connection refused


kubectl get endpoints <svc> shows empty or fewer endpoints


Proposed fix


Correct probe path/port OR adjust timeouts/initialDelay


If port mismatch: fix Service targetPort


Auto-fix (demo-safe)


Patch readiness probe to the correct path/port (from app’s known config) or raise timeout threshold


Guardrails: don’t weaken probes blindly; only apply approved “probe profiles” per service


5) OOMKilled: memory limit too low / sudden spike
Why it’s common: default limits too tight, traffic spike, memory leak, JVM/Node tuning.
Alert trigger


kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}


Restarts + memory usage near limit (if metrics-server/Prometheus present)


What the agent checks


kubectl describe pod last state reason OOMKilled


Metrics: container memory working set close to limit


Proposed fix


Increase memory limit (and request) by a controlled increment, or scale replicas if CPU-bound too


Auto-fix


“Bump memory limit by 25–50%” + restart rollout


Guardrails: cap maximum, require approval in prod, ensure namespace quota won’t be violated



Other issues:
DNS misconfiguration
SSL expiration/issues
503 Service Temporarily Unavailable or 502 Bad Gateway(same like 503 depends on the controller error code changes) - Service to pod misconfiguration - No endpoints available 
