# DevOps Use Cases Resolvable by Agentic AI

------------------------------------------------------------------------

## 1) CrashLoopBackOff due to Bad Config / Missing Env

**Why it's common** - Config drift\
- Wrong ConfigMap/Secret key\
- Typo in environment variable name\
- Bad feature flag

**Alert triggers**

``` promql
kube_pod_container_status_restarts_total increasing fast
```

``` promql
kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}
```

### What the agent checks

``` bash
kubectl describe pod <pod-name>
kubectl logs <pod-name> --previous
```

Common errors:

    missing required env VAR_X
    failed to load config file
    panic: ...

### Proposed fix

-   Identify missing env / wrong key\
-   Point to correct Secret/ConfigMap key

### Auto-fix (Safe)

-   Patch Deployment env var key or mount reference\
-   Rollout restart

**Guardrails** - Patch only whitelisted env keys\
- Restrict auto-fix to non-prod (demo)

------------------------------------------------------------------------

## 2) CreateContainerConfigError: Secret/ConfigMap Not Found

**Why it's common** - Renamed/deleted secret\
- Wrong namespace\
- Helm reinstall\
- ExternalSecrets delay

**Alert trigger**

``` promql
kube_pod_container_status_waiting_reason{reason="CreateContainerConfigError"}
```

### What the agent checks

``` bash
kubectl describe pod <pod-name>
```

Events may show:

    secret "X" not found
    configmap "Y" not found

### Proposed fix

-   Create missing Secret/ConfigMap\
-   Fix incorrect reference

### Auto-fix

-   Recreate from approved template\
-   Trigger ExternalSecret re-sync

**Guardrails** - Only from approved sources\
- Never expose secret values

------------------------------------------------------------------------

## 3) ImagePullBackOff

**Why it's common** - Wrong image tag\
- Rotated registry token\
- Missing pull secret

**Alert trigger**

``` promql
kube_pod_container_status_waiting_reason{reason=~"ErrImagePull|ImagePullBackOff"}
```

### What the agent checks

``` bash
kubectl describe pod <pod-name>
```

Events may show:

    manifest unknown
    pull access denied
    toomanyrequests

### Proposed fix

-   Rollback to last-known-good tag\
-   Fix/add imagePullSecret

### Auto-fix

-   Patch Deployment image tag\
-   Attach approved pull secret

**Guardrails** - Same repo/app only\
- Approval required in prod

------------------------------------------------------------------------

## 4) Readiness Probe Failing

**Why it's common** - Wrong path/port\
- Slow startup\
- Misconfigured service port

### What the agent checks

``` bash
kubectl describe pod <pod-name>
kubectl get endpoints <service-name>
```

Example:

    Readiness probe failed: HTTP 404/500
    connection refused

### Proposed fix

-   Correct probe path/port\
-   Adjust timeouts\
-   Fix Service targetPort

### Auto-fix

-   Patch readiness probe\
-   Apply approved probe profile

**Guardrails** - Do not weaken probes blindly

------------------------------------------------------------------------

## 5) OOMKilled

**Why it's common** - Tight limits\
- Traffic spike\
- Memory leak

**Alert trigger**

``` promql
kube_pod_container_status_last_terminated_reason{reason="OOMKilled"}
```

### What the agent checks

``` bash
kubectl describe pod <pod-name>
```

Look for:

    Reason: OOMKilled

### Proposed fix

-   Increase memory limit (25--50%)\
-   Scale replicas if needed

**Guardrails** - Cap maximum limit\
- Ensure namespace quota compliance

------------------------------------------------------------------------

## 6) DNS Misconfiguration

**Symptoms**

    lookup service.namespace.svc.cluster.local: no such host

**Agent checks**

``` bash
kubectl exec -it <pod> -- nslookup <service>
```

------------------------------------------------------------------------

## 7) SSL Certificate Expiration

**Symptoms** - TLS handshake failures\
- 502/503 from ingress

**Agent checks**

``` bash
kubectl describe certificate
kubectl describe ingress
```

------------------------------------------------------------------------

## 8) 503 / 502 Errors

**Common causes** - No endpoints\
- Service selector mismatch\
- targetPort mismatch

**Agent checks**

``` bash
kubectl get endpoints <service>
kubectl describe service <service>
kubectl logs <ingress-controller-pod>
```

------------------------------------------------------------------------
