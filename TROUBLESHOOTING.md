# Troubleshooting Guide

Common issues and solutions for both deployment methods.

---

## Bot Not Responding to Mentions

**Symptoms:** Bot doesn't react when mentioned in Slack

### Check Slack Configuration

1. **Verify Socket Mode is enabled:**
   - Go to https://api.slack.com/apps
   - Select your app → Socket Mode → Should be ON

2. **Verify Event Subscriptions:**
   - Event Subscriptions → Should be ON
   - Subscribe to bot events: `app_mention`
   - Click "Reinstall to Workspace" after any changes

3. **Verify OAuth Scopes:**
   - OAuth & Permissions → Bot Token Scopes:
     - `app_mentions:read`
     - `chat:write`
     - `channels:history`

4. **Verify bot is invited to channel:**
   ```
   /invite @kagent
   ```

### Check Bot Logs

**Method 1 (Kubernetes):**
```bash
kubectl logs -n kagent -l app=kagent-slack-bot --tail=50
```

**Method 2 (Laptop/Server):**
```bash
# If systemd service
sudo journalctl -u kagent-slack-bot -n 50

# If running manually
# Check terminal output
```

**Look for:**
- ✅ `Slack app initialized` - Tokens are valid
- ✅ `⚡ Bolt app is running!` - Socket Mode connected
- ✅ `🔔 Received app_mention` - Events are coming through

**If missing `Slack app initialized`:**
- Check tokens are correct
- Verify secret exists (Kubernetes): `kubectl get secret slack-credentials -n kagent`

**If missing `Bolt app is running!`:**
- Check app token (xapp-...) is correct
- Verify Socket Mode is enabled in Slack app settings

**If missing `Received app_mention`:**
- Reinstall app to workspace after config changes
- Check Event Subscriptions has `app_mention` event

---

## Connection Issues

### Method 1: Single Bot Per Cluster (Direct A2A - Port 8083)

**Error:** `Connection refused` or `No address associated with hostname`

**Solution 1: Verify Kagent is running**
```bash
# Check Kagent controller is running
kubectl get pods -n kagent

# Check service exists
kubectl get svc kagent-controller -n kagent
```

**Solution 2: Test from within cluster**
```bash
# Run test pod
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -n kagent -- \
  curl http://kagent-controller.kagent.svc.cluster.local:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

Should return JSON with agent info (not 404 or connection refused).

**Solution 3: Verify environment variables**
```bash
# Check deployment env vars
kubectl get deployment kagent-slack-bot -n kagent -o yaml | grep -A 5 "env:"

# Should have:
# - KAGENT_BASE_URL: http://kagent-controller.kagent.svc.cluster.local:8083
# - KAGENT_NAMESPACE: kagent
# - KAGENT_AGENT_NAME: k8s-agent
```

---

### Method 2: Multi-Cluster via AgentGateway (Port 8080)

**Error:** `Connection refused`, `Connection timeout`, or `No route to host`

**Solution 1: Test connectivity**
```bash
# Test each cluster endpoint
curl http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
curl http://192.168.1.201:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

Should return JSON, not connection error.

**Solution 2: Check network access**
```bash
# Ping cluster IPs
ping 192.168.1.200
ping 192.168.1.201

# Check port is open
nc -zv 192.168.1.200 8080
nc -zv 192.168.1.201 8080
```

**Common network issues:**
- ❌ Firewall blocking port 8080
- ❌ VPN not connected
- ❌ Wrong IP addresses in .env
- ❌ AgentGateway not running on clusters

**Solution 3: Verify AgentGateway is running**
```bash
# For each cluster, check AgentGateway pods
kubectl get pods -n kagent | grep agentgateway

# Check AgentGateway service
kubectl get svc -n kagent | grep agentgateway
```

**Solution 4: Check environment variables**
```bash
# View .env configuration
grep KAGENT .env | grep -v "^#"

# Should have:
# ENABLE_MULTI_CLUSTER=true
# KAGENT_CLUSTERS=test,dev
# KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
# KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
```

---

## Pod Not Starting (Kubernetes)

**Symptoms:** Pod stuck in CrashLoopBackOff or ImagePullBackOff

### Check Pod Status
```bash
kubectl get pods -n kagent -l app=kagent-slack-bot
kubectl describe pod -n kagent -l app=kagent-slack-bot
```

### Common Issues

**ImagePullBackOff:**
```bash
# Check image name in deployment
kubectl get deployment kagent-slack-bot -n kagent -o yaml | grep image:

# Verify image exists
docker pull matcham89/kagent-slack-bot:1.0.1
```

**CrashLoopBackOff:**
```bash
# Check logs
kubectl logs -n kagent -l app=kagent-slack-bot --tail=100

# Common causes:
# - Missing secret (slack-credentials)
# - Invalid tokens
# - Missing environment variables
```

**Secret not found:**
```bash
# Check secret exists
kubectl get secret slack-credentials -n kagent

# If missing, create it:
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-your-token' \
  --from-literal=app-token='xapp-your-token' \
  --namespace=kagent
```

**Pending (can't schedule):**
```bash
# Check cluster resources
kubectl describe node

# Look for resource pressure or taints preventing scheduling
```

---

## Local Development Issues

### Port-Forward Disconnects

**Error:** `connection refused` when bot tries to connect

**Solution:**
```bash
# Check port-forward is running
lsof -i :8083

# If not, restart it
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
```

**Tip:** Use tmux or screen to keep port-forward running in background

### Wrong Namespace/Agent

**Error:** `404 Not Found`

**Solution:**
```bash
# Check what's deployed
kubectl get agents -A

# Update .env with correct values
KAGENT_A2A_URL=http://localhost:8083/api/a2a/<NAMESPACE>/<AGENT-NAME>
```

---

## Cluster Detection Not Working (Multi-Cluster)

**Symptoms:** Bot doesn't route to correct cluster

### How Cluster Detection Works

The bot looks for these keywords in messages:
- `test`, `testing` → routes to test cluster
- `dev`, `development` → routes to dev cluster
- `prod`, `production` → routes to prod cluster

### Examples

✅ **Works:**
- `@kagent list pods in test cluster`
- `@kagent check dev namespace`
- `@kagent show production deployments`

❌ **Doesn't work (uses default cluster):**
- `@kagent list pods`
- `@kagent check namespaces`

### Check Logs

```bash
# Look for cluster detection
sudo journalctl -u kagent-slack-bot -n 20 | grep "Detected cluster"

# Should see:
# 🎯 Detected cluster: test
# OR
# 🤷 No cluster detected in message
```

### Verify Configuration

```bash
# Check clusters are defined
grep KAGENT_CLUSTERS .env
# Should show: KAGENT_CLUSTERS=test,dev,prod

# Check default cluster
grep KAGENT_DEFAULT_CLUSTER .env
```

---

## Slack Tokens Invalid

**Error:** `invalid_auth` or bot not connecting

### Verify Tokens

**Bot Token (xoxb-...):**
1. Go to https://api.slack.com/apps
2. Select your app → OAuth & Permissions
3. Copy "Bot User OAuth Token"
4. Starts with `xoxb-`

**App Token (xapp-...):**
1. Go to https://api.slack.com/apps
2. Select your app → Basic Information → App-Level Tokens
3. Create token with `connections:write` scope
4. Copy token (starts with `xapp-`)

### Update Tokens

**Kubernetes:**
```bash
# Delete old secret
kubectl delete secret slack-credentials -n kagent

# Create new secret
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-new-token' \
  --from-literal=app-token='xapp-new-token' \
  --namespace=kagent

# Restart deployment
kubectl rollout restart deployment/kagent-slack-bot -n kagent
```

**Laptop/Server:**
```bash
# Edit .env
nano .env

# Update tokens:
SLACK_BOT_TOKEN=xoxb-new-token
SLACK_APP_TOKEN=xapp-new-token

# Restart service
sudo systemctl restart kagent-slack-bot
```

---

## Performance Issues

### Slow Responses

**Symptoms:** Bot takes long time to respond

**Causes:**
- Kagent processing time (AI inference)
- Network latency
- Kubernetes resource constraints

**Solutions:**

1. **Check Kagent logs:**
   ```bash
   kubectl logs -n kagent -l app=kagent-controller -f
   ```

2. **Check bot resource usage:**
   ```bash
   kubectl top pod -n kagent -l app=kagent-slack-bot
   ```

3. **Increase resource limits:**
   Edit deployment and increase memory/CPU limits

### Timeout Errors

**Error:** `Request timed out. Please try again.`

**Current timeout:** 5 minutes (300 seconds)

**Solution:**
This is expected for very complex queries. Ask the agent to break down the task into smaller steps.

---

## Getting More Help

### Collect Debug Information

Before asking for help, collect this info:

**Method 1 (Kubernetes):**
```bash
# Pod status
kubectl get pods -n kagent -l app=kagent-slack-bot

# Recent logs
kubectl logs -n kagent -l app=kagent-slack-bot --tail=100

# Deployment config
kubectl get deployment kagent-slack-bot -n kagent -o yaml

# Secret exists?
kubectl get secret slack-credentials -n kagent
```

**Method 2 (Laptop/Server):**
```bash
# Service status
sudo systemctl status kagent-slack-bot

# Recent logs
sudo journalctl -u kagent-slack-bot -n 100

# Environment config (redact tokens!)
grep -v "TOKEN" .env | grep -v "^#"
```

### Where to Get Help

- **GitHub Issues:** https://github.com/your-org/kagent-slack-bot/issues
- **Kagent Issues:** https://github.com/kagent-ai/kagent/issues
- **Slack API Docs:** https://api.slack.com/docs

---

## Quick Reference

### Check Bot Status

| Deployment | Command |
|------------|---------|
| Kubernetes | `kubectl logs -n kagent -l app=kagent-slack-bot -f` |
| Systemd | `sudo systemctl status kagent-slack-bot` |
| Manual | Check terminal output |

### Test Endpoints

| Method | Test Command |
|--------|--------------|
| Method 1 (Port 8083) | `curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json` |
| Method 2 (Port 8080) | `curl http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json` |

### Restart Bot

| Deployment | Command |
|------------|---------|
| Kubernetes | `kubectl rollout restart deployment/kagent-slack-bot -n kagent` |
| Systemd | `sudo systemctl restart kagent-slack-bot` |
| Manual | Ctrl+C then `python slack_bot.py` |
