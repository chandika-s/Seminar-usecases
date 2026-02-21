# EKS Agentic DevOps Agent Demo Guide

This guide walks through deterministic failure simulations for:

1.  CrashLoopBackOff (bad config / missing env)
2.  CreateContainerConfigError (missing Secret/ConfigMap)
3.  ImagePullBackOff (bad tag / registry auth)
4.  Readiness probe failures
5.  OOMKilled (memory limit exceeded)

------------------------------------------------------------------------

# Pre-flight Check

``` bash
kubectl get deploy,pod,svc -l app=demo-app
kubectl get endpoints demo-app
kubectl port-forward svc/demo-app 8080:80
```

Verify health:

``` bash
curl -i http://localhost:8080/
curl -i http://localhost:8080/readyz
curl -i http://localhost:8080/healthz
```

------------------------------------------------------------------------

# 1️⃣ CrashLoopBackOff (Missing Env)

Trigger:

``` bash
kubectl set env deploy/demo-app REQUIRE_ENV=1 --overwrite
kubectl set env deploy/demo-app VAR_X- 2>/dev/null || true
kubectl rollout status deploy/demo-app
```

Observe:

``` bash
kubectl get pods -l app=demo-app
kubectl logs -l app=demo-app --previous
kubectl describe pod -l app=demo-app
```

Fix:

``` bash
kubectl set env deploy/demo-app VAR_X=demo-value --overwrite
kubectl rollout status deploy/demo-app
```

------------------------------------------------------------------------

# 2️⃣ CreateContainerConfigError (Missing Secret)

Trigger:

``` bash
kubectl patch deploy demo-app --type='json' -p='[
  {"op":"add","path":"/spec/template/spec/containers/0/env/-","value":{
    "name":"VAR_X",
    "valueFrom":{"secretKeyRef":{"name":"demo-missing-secret","key":"VAR_X"}}
  }}
]'
```

Observe:

``` bash
kubectl describe pod -l app=demo-app
```

Fix:

``` bash
kubectl create secret generic demo-missing-secret --from-literal=VAR_X=fixed
kubectl rollout status deploy/demo-app
```

------------------------------------------------------------------------

# 3️⃣ ImagePullBackOff

Trigger (bad tag):

``` bash
kubectl set image deploy/demo-app demo-app=your-repo/demo-app:does-not-exist
```

Observe:

``` bash
kubectl describe pod -l app=demo-app
```

Fix:

``` bash
kubectl rollout undo deploy/demo-app
kubectl rollout status deploy/demo-app
```

------------------------------------------------------------------------

# 4️⃣ Readiness Probe Failure

Trigger:

``` bash
kubectl set env deploy/demo-app FORCE_NOT_READY=1 --overwrite
kubectl rollout status deploy/demo-app
```

Observe:

``` bash
kubectl get endpoints demo-app
kubectl describe pod -l app=demo-app
```

Fix:

``` bash
kubectl set env deploy/demo-app FORCE_NOT_READY=0 --overwrite
kubectl rollout status deploy/demo-app
```

------------------------------------------------------------------------

# 5️⃣ OOMKilled (Deterministic)

Set tight memory limit and hog memory:

``` bash
kubectl set resources deploy/demo-app -c demo-app --limits=memory=32Mi --requests=memory=16Mi
kubectl set env deploy/demo-app MEMORY_HOG_MB=200 --overwrite
kubectl rollout status deploy/demo-app
```

Watch restarts:

``` bash
kubectl get pods -l app=demo-app -w
```

Verify termination reason:

``` bash
POD=$(kubectl get pod -l app=demo-app -o jsonpath='{.items[0].metadata.name}')
kubectl get pod "$POD" -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
kubectl describe pod "$POD"
```

Expected:

-   Reason: OOMKilled
-   Exit Code: 137

Fix (bump memory):

``` bash
kubectl set resources deploy/demo-app -c demo-app --limits=memory=128Mi --requests=memory=64Mi
kubectl rollout status deploy/demo-app
```

------------------------------------------------------------------------

# Cleanup (Restore Healthy State)

``` bash
kubectl set env deploy/demo-app MEMORY_HOG_MB- 2>/dev/null || true
kubectl set resources deploy/demo-app -c demo-app --limits=memory=64Mi --requests=memory=32Mi
kubectl rollout restart deploy/demo-app
```

------------------------------------------------------------------------

# Demo Narrative Flow

1.  Show healthy service.
2.  Trigger CrashLoopBackOff → show logs → fix.
3.  Trigger missing Secret → show Events → fix.
4.  Trigger ImagePullBackOff → rollback.
5.  Trigger Readiness failure → endpoints empty → fix.
6.  Trigger OOMKilled → show Exit Code 137 → bump memory → recover.

------------------------------------------------------------------------

End of Guide.
