# Kubernetes Deployment Guide - Method 1: Single Bot Per Cluster

Deploy one Kagent Slack bot instance per cluster. The bot runs inside the cluster and connects directly to the Kagent controller via the A2A protocol (port 8083).

## When to Use This Method

- You want isolated, independent bot instances for each cluster
- Each cluster has its own dedicated Slack bot (e.g., @kagent-test, @kagent-prod)
- Simple setup with direct A2A connection
- No AgentGateway required

## Architecture

```
Slack → Bot (in cluster) → Kagent Controller (port 8083) → k8s-agent → Kubernetes API
```

The bot runs as a pod in the same cluster as Kagent, using in-cluster service discovery.

---

## Prerequisites

- **Kubernetes cluster** with Kagent installed
- **kubectl** configured and connected to your cluster
- **Slack App** configured (see [README.md](README.md#slack-app-setup))
- **Docker image** - Use `matcham89/kagent-slack-bot:1.0.1` or build your own

---

## Quick Deployment (3 Steps)

### Step 1: Create Slack Credentials Secret

Create a Kubernetes secret with your Slack tokens:

```bash
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-your-bot-token-here' \
  --from-literal=app-token='xapp-your-app-token-here' \
  --namespace=kagent
```

**Get your tokens:**
- Bot token (xoxb-...): Slack App → OAuth & Permissions → Bot User OAuth Token
- App token (xapp-...): Slack App → Basic Information → App-Level Tokens

**Verify secret was created:**
```bash
kubectl get secret slack-credentials -n kagent
```

### Step 2: Deploy the Bot

```bash
kubectl apply -f k8s-deployment-single-cluster.yaml
```

This creates a Deployment with:
- 1 replica running in the `kagent` namespace
- Direct A2A connection to `kagent-controller` service (port 8083)
- Security-hardened pod (restricted pod security standard)

### Step 3: Verify Deployment

```bash
# Check pod is running
kubectl get pods -n kagent -l app=kagent-slack-bot

# View logs
kubectl logs -n kagent -l app=kagent-slack-bot -f
```

**Expected output:**
```
✅ Slack app initialized
🚀 Starting Kagent Slack Bot...
   Kagent: http://kagent-controller.kagent.svc.cluster.local:8083
⚡️ Kagent Slack Bot is running!
⚡️ Bolt app is running!
```

---

## Test in Slack

```
# Invite the bot to a channel
/invite @kagent

# Ask questions
@kagent list all namespaces
@kagent what pods are running?
@kagent show me logs for nginx
```

The bot should respond with context - it maintains conversation history within each Slack thread!

---

## Configuration

### Update Namespace or Agent

Edit `k8s-deployment-single-cluster.yaml` to customize:

```yaml
env:
# Change the namespace where Kagent is deployed
- name: KAGENT_NAMESPACE
  value: "kagent"  # Change to your namespace

# Change the agent name
- name: KAGENT_AGENT_NAME
  value: "k8s-agent"  # Change to your agent name

# Update service URL if needed
- name: KAGENT_BASE_URL
  value: "http://kagent-controller.kagent.svc.cluster.local:8083"
```

**Apply changes:**
```bash
kubectl apply -f k8s-deployment-single-cluster.yaml
```

### Update Resource Limits

Default resources:

```yaml
resources:
  requests:
    memory: "128Mi"  # Minimum memory
    cpu: "100m"      # 0.1 CPU core
  limits:
    memory: "256Mi"  # Maximum memory
    cpu: "200m"      # 0.2 CPU cores
```

**Adjust based on your needs:**
- **Small workspace** (< 10 users): Default values are fine
- **Large workspace** (100+ users): Increase to `512Mi` memory, `500m` CPU

### Multiple Replicas (High Availability)

For failover:

```yaml
spec:
  replicas: 2  # Run 2 pods for redundancy
```

**Note:** Slack Socket Mode maintains one connection, so multiple replicas provide failover but won't distribute load.

---

## Building Custom Image

If you modified `slack_bot.py` and want to deploy your changes:

### Option 1: Use build.sh

```bash
# Set your registry
export REGISTRY=docker.io/your-username
export TAG=v1.0.0

# Build and push multi-platform image
./build.sh
```

### Option 2: Manual Build

```bash
# Build
docker build -t your-registry/kagent-slack-bot:latest .

# Push
docker push your-registry/kagent-slack-bot:latest

# Update image in k8s-deployment-single-cluster.yaml
# Then deploy
kubectl apply -f k8s-deployment-single-cluster.yaml
```

---

## Updating Slack Tokens

If you need to rotate Slack tokens:

```bash
# Delete old secret
kubectl delete secret slack-credentials -n kagent

# Create new secret with updated tokens
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-new-token' \
  --from-literal=app-token='xapp-new-token' \
  --namespace=kagent

# Restart deployment to pick up new secret
kubectl rollout restart deployment/kagent-slack-bot -n kagent

# Watch rollout
kubectl rollout status deployment/kagent-slack-bot -n kagent
```

---

## Monitoring

### View Logs

```bash
# Follow logs in real-time
kubectl logs -n kagent -l app=kagent-slack-bot -f

# View last 100 lines
kubectl logs -n kagent -l app=kagent-slack-bot --tail=100

# View logs from specific pod
kubectl logs -n kagent kagent-slack-bot-xxxxx-xxxxx
```

**Look for context management logs:**
```
🔔 Received app_mention event
🆕 Starting new conversation
🔄 Using existing contextId: 7d5e0706-...
📊 Processed 7 events from stream
💬 Found agent response
```

### Check Pod Status

```bash
# List pods
kubectl get pods -n kagent -l app=kagent-slack-bot

# Describe pod (shows events and errors)
kubectl describe pod -n kagent -l app=kagent-slack-bot

# Check resource usage
kubectl top pod -n kagent -l app=kagent-slack-bot
```

### View Events

```bash
kubectl get events -n kagent --sort-by='.lastTimestamp' | grep kagent-slack-bot
```

---

## Troubleshooting

### Pod Not Starting

**Check events:**
```bash
kubectl describe pod -n kagent -l app=kagent-slack-bot
```

**Common issues:**
- **ImagePullBackOff**: Docker image not accessible
  - Solution: Check image name, ensure registry access
- **CrashLoopBackOff**: Bot crashing on startup
  - Solution: Check logs with `kubectl logs`
- **Pending**: Can't schedule pod
  - Solution: Check cluster resources with `kubectl describe node`

### Bot Not Responding

**Check logs:**
```bash
kubectl logs -n kagent -l app=kagent-slack-bot --tail=50
```

**Look for:**
- `✅ Slack app initialized` - Tokens are valid
- `⚡️ Bolt app is running!` - Socket Mode connected
- `🔔 Received app_mention event` - Events are coming through

**If no events received:**
1. Verify Socket Mode is enabled in Slack app settings
2. Check Event Subscriptions has `app_mention` event
3. Reinstall app to workspace after config changes
4. Check Slack tokens in secret are correct

### Can't Connect to Kagent

**Check service exists:**
```bash
kubectl get svc kagent-controller -n kagent
```

**Test from within cluster:**
```bash
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://kagent-controller.kagent.svc.cluster.local:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**Should return agent info** (not 404 or connection refused).

**If connection fails:**
- Verify Kagent is running: `kubectl get pods -n kagent`
- Check Kagent service: `kubectl get svc -n kagent`
- Verify namespace and agent name in deployment yaml

### Secret Not Found

```bash
# Check secret exists
kubectl get secret slack-credentials -n kagent

# View secret (base64 encoded)
kubectl get secret slack-credentials -n kagent -o yaml

# Check secret has correct keys
kubectl get secret slack-credentials -n kagent -o jsonpath='{.data}' | jq keys
# Should show: ["app-token", "bot-token"]
```

---

## Security Best Practices

### Namespace Isolation

Deploy bot in same namespace as Kagent for network policy isolation:

```bash
# Ensure kagent namespace exists
kubectl get namespace kagent

# Deploy in kagent namespace
kubectl apply -f k8s-deployment-single-cluster.yaml
```

### Limit Permissions

The bot doesn't need any Kubernetes API permissions. The default ServiceAccount is fine, and `automountServiceAccountToken: false` prevents unnecessary token mounting.

### Pod Security Standards

The deployment is configured for the `restricted` pod security standard:

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop:
      - ALL
```

Verify your namespace enforces pod security:

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: kagent
  labels:
    pod-security.kubernetes.io/enforce: restricted
```

---

## Scaling Considerations

### Horizontal Scaling

**Not recommended** for this bot because:
- Slack Socket Mode = one connection per bot
- Multiple replicas won't distribute load
- Can cause duplicate message processing

**Use replicas=1** or **replicas=2** (for failover only).

### Vertical Scaling

Increase resources if needed:

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "200m"
  limits:
    memory: "512Mi"
    cpu: "500m"
```

---

## Uninstalling

```bash
# Delete deployment
kubectl delete deployment kagent-slack-bot -n kagent

# Delete secret
kubectl delete secret slack-credentials -n kagent
```

---

## Next Steps

- **Multi-cluster setup**: See [LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md) for Method 2
- **Local development**: See [LOCAL_DEV.md](LOCAL_DEV.md)
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Support

- **Logs not showing up?** Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Questions?** Open an issue in the GitHub repository
- **Kagent Issues**: https://github.com/kagent-ai/kagent/issues
