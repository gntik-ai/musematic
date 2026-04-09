# Quickstart: Redis Cache and Hot State Deployment

**Feature**: 002-redis-cache-hot-state  
**Date**: 2026-04-09

---

## Prerequisites

- Kubernetes cluster with `kubectl` configured
- `helm` 3.x
- Bitnami Helm repo added: `helm repo add bitnami https://charts.bitnami.com/bitnami`
- Python 3.12+ with redis-py 5.x installed (`pip install redis[hiredis]`)
- Go 1.22+ with go-redis v9 (`go get github.com/redis/go-redis/v9`)

Install the control-plane package before running the Python client or tests:

```bash
pip install -e ./apps/control-plane
```

---

## 1. Deploy Redis Cluster (Production)

```bash
# Create the Redis password secret
kubectl create secret generic redis-credentials \
  --from-literal=password="$(openssl rand -base64 32)" \
  -n platform-data --create-namespace

# Install the Helm chart for production
helm install musematic-redis deploy/helm/redis \
  -n platform-data \
  -f deploy/helm/redis/values.yaml \
  -f deploy/helm/redis/values-prod.yaml

# Verify all 6 pods are running
kubectl get pods -n platform-data -l app.kubernetes.io/name=redis-cluster

# Verify cluster health
kubectl exec -it musematic-redis-cluster-0 -n platform-data -- \
  redis-cli -a "$(kubectl get secret redis-credentials -n platform-data -o jsonpath='{.data.password}' | base64 -d)" \
  cluster info
```

---

## 2. Deploy Redis (Development)

```bash
kubectl create secret generic redis-credentials \
  --from-literal=password=dev-password \
  -n platform-data --create-namespace

helm install musematic-redis deploy/helm/redis \
  -n platform-data \
  -f deploy/helm/redis/values.yaml \
  -f deploy/helm/redis/values-dev.yaml
```

---

## 3. Test Basic Operations

```bash
# Port-forward to local
kubectl port-forward svc/musematic-redis-cluster 6379:6379 -n platform-data &

# Test SET/GET
redis-cli -a <password> SET test_key test_value
redis-cli -a <password> GET test_key
# Expected: "test_value"

# Test session pattern
redis-cli -a <password> SET "session:user1:sess1" '{"email":"alice@example.com"}' EX 1800
redis-cli -a <password> GET "session:user1:sess1"
redis-cli -a <password> TTL "session:user1:sess1"
```

---

## 4. Test Budget Decrement (Lua Script)

```bash
# Initialize a budget hash
redis-cli -a <password> HSET "budget:exec1:step1" \
  max_tokens 1000 used_tokens 0 \
  max_rounds 10 used_rounds 0 \
  max_cost 5.0 used_cost 0 \
  max_time_ms 30000 start_time $(date +%s%3N)

# Decrement tokens (verify atomic operation)
redis-cli -a <password> EVAL "$(cat lua/budget_decrement.lua)" \
  1 "budget:exec1:step1" $(date +%s%3N) tokens 100

# Check remaining
redis-cli -a <password> HGETALL "budget:exec1:step1"
```

---

## 5. Test Distributed Lock

```bash
# Acquire lock
redis-cli -a <password> SET "lock:scheduler:main" "token-abc123" NX EX 10
# Expected: OK

# Attempt duplicate acquire
redis-cli -a <password> SET "lock:scheduler:main" "token-xyz" NX EX 10
# Expected: (nil) — lock held

# Release (would use Lua script in production for token verification)
redis-cli -a <password> DEL "lock:scheduler:main"
```

---

## 6. Test Leaderboard

```bash
# Add hypotheses with Elo scores
redis-cli -a <password> ZADD "leaderboard:tournament1" 1500 "hyp-a" 1650 "hyp-b" 1400 "hyp-c" 1720 "hyp-d"

# Get top 3
redis-cli -a <password> ZREVRANGE "leaderboard:tournament1" 0 2 WITHSCORES
# Expected: hyp-d (1720), hyp-b (1650), hyp-a (1500)

# Get rank of specific hypothesis
redis-cli -a <password> ZREVRANK "leaderboard:tournament1" "hyp-c"
# Expected: 3 (0-indexed, last place)
```

---

## 7. Test Failover (Production Only)

```bash
# Identify current masters
kubectl exec -it musematic-redis-cluster-0 -n platform-data -- \
  redis-cli -a <password> cluster nodes | grep master

# Delete a master pod
kubectl delete pod musematic-redis-cluster-0 -n platform-data

# Watch failover (should complete in <10s)
kubectl exec -it musematic-redis-cluster-1 -n platform-data -- \
  redis-cli -a <password> cluster info
# Expected: cluster_state:ok
```

---

## 8. Verify Network Policy (Production Only)

```bash
# From authorized namespace (should succeed)
kubectl run -n platform-control --rm -it test-redis --image=redis:7 --restart=Never -- \
  redis-cli -h musematic-redis-cluster.platform-data -a <password> PING

# From unauthorized namespace (should timeout/refuse)
kubectl run -n default --rm -it test-redis --image=redis:7 --restart=Never -- \
  redis-cli -h musematic-redis-cluster.platform-data -a <password> PING
```

---

## 9. Verify Prometheus Metrics (Production Only)

```bash
kubectl port-forward svc/musematic-redis-cluster-metrics 9121:9121 -n platform-data &
curl -s http://localhost:9121/metrics | grep redis_up
# Expected: redis_up 1

curl -s http://localhost:9121/metrics | grep redis_memory_used_bytes
```

---

## 10. Using the Python Client

```python
from platform.common.clients.redis import AsyncRedisClient

client = AsyncRedisClient(nodes=["musematic-redis-cluster.platform-data:6379"])
await client.initialize()

# Session
await client.set_session("user1", "sess1", {"email": "alice@example.com"}, ttl_seconds=1800)
session = await client.get_session("user1", "sess1")

# Budget
result = await client.decrement_budget("exec1", "step1", "tokens", 100)
if not result.allowed:
    print("Budget exhausted!")

# Rate limit
rl = await client.check_rate_limit("api", "user1", limit=100, window_ms=60000)
if not rl.allowed:
    print(f"Rate limited. Retry in {rl.retry_after_ms}ms")

# Lock
lock = await client.acquire_lock("scheduler", "main", ttl_seconds=10)
if lock.success:
    try:
        # do work
        pass
    finally:
        await client.release_lock("scheduler", "main", lock.token)

await client.close()
```

---

## 11. Run Redis Integration Tests Locally

```bash
export REDIS_TEST_MODE=standalone
export REDIS_URL=redis://localhost:6379
python -m pytest apps/control-plane/tests/integration/test_redis_*.py -v
```
