# Local Python Deployment Guide

Deploy the Kagent Slack bot by running Python locally on your laptop or server.

**This guide covers:**
- ✅ Single-cluster setup (one cluster)
- ✅ Multi-cluster setup (optional, multiple clusters)
- ✅ Running Python directly (no systemd/docker)

---

## When to Use This Method

**Single-Cluster:**
- You want to connect to ONE Kubernetes cluster
- Simple setup with direct A2A connection (port 8083)
- Bot runs on your laptop/server, connects to Kagent controller

**Multi-Cluster (Optional):**
- You want ONE Slack bot for multiple clusters
- Users specify cluster keywords in messages (e.g., "test", "dev", "prod")
- Requires AgentGateway deployed on each cluster (port 8080)

---

## Prerequisites

### Required
- **Python 3.13+** installed
- **Slack workspace** admin access
- **Git** for cloning repository

### For Single-Cluster
- **Network access** to Kagent controller (port 8083)
  - Either via port-forward: `kubectl port-forward -n kagent svc/kagent-controller 8083:8083`
  - Or direct access to cluster endpoint

### For Multi-Cluster (Optional)
- **Network access** to AgentGateway on each cluster (port 8080)
- **AgentGateway** deployed on each cluster
- **VPN/network** access to all cluster IPs

---

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Get Slack Tokens

See [SECRETS.md](SECRETS.md) for detailed instructions.

**Quick version:**
1. Go to https://api.slack.com/apps
2. Create New App → From scratch
3. Enable Socket Mode → Generate token (xapp-...) with `connections:write` scope
4. OAuth & Permissions → Add scopes: `app_mentions:read`, `chat:write`, `channels:history`
5. Install App → Copy Bot User OAuth Token (xoxb-...)

### 3. Configure (Choose Your Setup)

<details>
<summary><b>Option A: Single-Cluster Setup</b> (Click to expand)</summary>

```bash
# Copy example config
cp .env.example .env

# Edit .env
nano .env
```

**Configuration:**
```bash
# Deployment mode
ENABLE_MULTI_CLUSTER=false

# Kagent endpoint (choose one method)
# Method 1: Full URL (recommended)
KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent

# Method 2: Separate components (alternative)
# KAGENT_BASE_URL=http://localhost:8083
# KAGENT_NAMESPACE=kagent
# KAGENT_AGENT_NAME=k8s-agent
```

**Set secrets as environment variables:**
```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_APP_TOKEN="xapp-your-app-token"
```

**If using port-forward (local development):**
```bash
# In another terminal, keep this running
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
```

</details>

<details>
<summary><b>Option B: Multi-Cluster Setup</b> (Click to expand)</summary>

```bash
# Copy example config
cp .env.example .env

# Edit .env
nano .env
```

**Configuration:**
```bash
# Deployment mode
ENABLE_MULTI_CLUSTER=true

# Kagent namespace (same across all clusters)
KAGENT_NAMESPACE=kagent

# Define clusters (comma-separated)
KAGENT_CLUSTERS=test,dev,prod

# Default cluster when no keyword detected
KAGENT_DEFAULT_CLUSTER=test

# Agent name (same on all clusters)
KAGENT_AGENT_PATTERN=k8s-agent

# AgentGateway endpoints (port 8080)
KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
KAGENT_PROD_BASE_URL=http://192.168.1.202:8080

# Optional: Custom aliases for cluster detection
KAGENT_TEST_ALIASES=testing,tst,test-cluster
KAGENT_DEV_ALIASES=development,develop,dev-cluster
KAGENT_PROD_ALIASES=production,prd,prod-cluster
```

**Set secrets as environment variables:**
```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_APP_TOKEN="xapp-your-app-token"
```

</details>

### 4. Test Connection

**Single-cluster:**
```bash
# Test Kagent endpoint
curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**Multi-cluster:**
```bash
# Test each cluster endpoint
curl http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
curl http://192.168.1.201:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
curl http://192.168.1.202:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**Expected output:** JSON with agent metadata (not 404 or connection error).

### 5. Run the Bot

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Run the bot
python slack_bot.py
```

**Expected output (Single-cluster):**
```
🚀 Initializing Kagent Slack Bot...
📋 Loading configuration...
🔧 Single-cluster mode
   Endpoint: http://localhost:8083/api/a2a/kagent/k8s-agent/
✅ Configuration validated
✅ Slack app initialized
🎬 Starting Kagent Slack Bot...
   Mode: Single-cluster
   Endpoint: http://localhost:8083/api/a2a/kagent/k8s-agent/
   Max context tokens: 300,000
   Request timeout: 300s
   Log level: INFO
⚡ Bot is running! Waiting for @mentions...
   Press Ctrl+C to stop
```

**To stop the bot:**
- Press `Ctrl+C` - Bot will shutdown gracefully
- You'll see: `🛑 Shutting down gracefully... Bot stopped`

**Expected output (Multi-cluster):**
```
🚀 Initializing Kagent Slack Bot...
📋 Loading configuration...
🌐 Multi-cluster routing mode enabled
   Clusters: test, dev, prod
   Default: test
   test: http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/
   dev: http://192.168.1.201:8080/api/a2a/kagent/k8s-agent/
   prod: http://192.168.1.202:8080/api/a2a/kagent/k8s-agent/
✅ Configuration validated
✅ Slack app initialized
🎬 Starting Kagent Slack Bot...
   Mode: Multi-cluster
   Clusters: test, dev, prod
   Default: test
   Max context tokens: 300,000
   Request timeout: 300s
   Log level: INFO
⚡ Bot is running! Waiting for @mentions...
   Press Ctrl+C to stop
```

### 6. Test in Slack

**Invite the bot:**
```
/invite @kagent
```

**Single-cluster usage:**
```
@kagent help
@kagent list namespaces
@kagent what pods are running?
@kagent context info
```

**Multi-cluster usage:**
```
@kagent help
@kagent list namespaces in test cluster
@kagent what pods are running in dev?
@kagent show prod deployments
@kagent check status  ← Uses default cluster
```

---

## Configuration Details

### Environment Variables

**Required (set as environment variables, NOT in .env):**
```bash
export SLACK_BOT_TOKEN="xoxb-..."      # Slack bot OAuth token
export SLACK_APP_TOKEN="xapp-..."      # Slack app-level token
```

**Optional configuration (can be in .env):**
```bash
REQUEST_TIMEOUT=300              # Request timeout in seconds (default: 300)
MAX_CONTEXT_TOKENS=300000        # Max tokens before warning (default: 300k)
LOG_LEVEL=INFO                   # Log level: DEBUG, INFO, WARNING, ERROR
```

### Single-Cluster Configuration

**Option 1: Full URL (Recommended)**
```bash
ENABLE_MULTI_CLUSTER=false
KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent
```

**Option 2: Separate Components**
```bash
ENABLE_MULTI_CLUSTER=false
KAGENT_BASE_URL=http://localhost:8083
KAGENT_NAMESPACE=kagent
KAGENT_AGENT_NAME=k8s-agent
```

**For in-cluster Kagent controller:**
```bash
KAGENT_A2A_URL=http://kagent-controller.kagent.svc.cluster.local:8083/api/a2a/kagent/k8s-agent
```

**For local development with port-forward:**
```bash
KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent
```

### Multi-Cluster Configuration

**Pattern-based (same agent name on all clusters):**
```bash
ENABLE_MULTI_CLUSTER=true
KAGENT_NAMESPACE=kagent
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test
KAGENT_AGENT_PATTERN=k8s-agent

# Base URLs for each cluster
KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
KAGENT_PROD_BASE_URL=http://192.168.1.202:8080
```

**URL-based (different agent names per cluster):**
```bash
ENABLE_MULTI_CLUSTER=true
KAGENT_NAMESPACE=kagent
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test

# Full URLs for each cluster
KAGENT_TEST_URL=http://192.168.1.200:8080/api/a2a/kagent/k8s-agent-test/
KAGENT_DEV_URL=http://192.168.1.201:8080/api/a2a/kagent/k8s-agent-dev/
KAGENT_PROD_URL=http://192.168.1.202:8080/api/a2a/kagent/k8s-agent-prod/
```

**Custom aliases:**
```bash
# Add custom keywords for cluster detection
KAGENT_TEST_ALIASES=testing,tst,test-cluster,qa
KAGENT_DEV_ALIASES=development,develop,dev-cluster
KAGENT_PROD_ALIASES=production,prd,prod-cluster,live
```

---

## Running in Background

### Using nohup

```bash
# Start bot in background
nohup python slack_bot.py > kagent-bot.log 2>&1 &

# Save process ID
echo $! > kagent-bot.pid

# View logs
tail -f kagent-bot.log

# Stop bot
kill $(cat kagent-bot.pid)
```

### Using screen

```bash
# Start screen session
screen -S kagent

# Run bot
python slack_bot.py

# Detach: Ctrl+A, then D

# Reattach later
screen -r kagent

# Stop bot: Ctrl+C in screen session
```

### Using tmux

```bash
# Start tmux session
tmux new -s kagent

# Run bot
python slack_bot.py

# Detach: Ctrl+B, then D

# Reattach later
tmux attach -t kagent

# Stop bot: Ctrl+C in tmux session
```

---

## Managing the Bot

### Start Bot

```bash
source venv/bin/activate
python slack_bot.py
```

### Stop Bot

**If running in foreground:**
```bash
# Press Ctrl+C
# You'll see graceful shutdown message:
# 🛑 Shutting down gracefully...
#    Bot stopped
```

**If running in background:**
```bash
# Find process
ps aux | grep slack_bot.py

# Kill process gracefully
kill <PID>

# Or if you saved PID
kill $(cat kagent-bot.pid)

# Force kill (only if graceful doesn't work)
kill -9 $(cat kagent-bot.pid)
```

### Restart Bot

```bash
# Stop (Ctrl+C or kill)
# Then start again
python slack_bot.py
```

### View Logs

**If using nohup:**
```bash
tail -f kagent-bot.log
```

**If running in foreground:**
Logs appear in terminal

---

## Updating

### Update Code

```bash
# Pull latest changes
git pull

# Activate environment
source venv/bin/activate

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart bot (stop and start)
```

### Update Configuration

```bash
# Edit .env
nano .env

# Update environment variables
export SLACK_BOT_TOKEN="xoxb-new-token"
export SLACK_APP_TOKEN="xapp-new-token"

# Restart bot
```

---

## Troubleshooting

### Bot Won't Start

**Check Python version:**
```bash
python3 --version  # Should be 3.13+
```

**Check dependencies:**
```bash
source venv/bin/activate
pip install -r requirements.txt
```

**Check configuration:**
```bash
# View current config (without secrets)
grep -v "TOKEN" .env | grep -v "^#" | grep -v "^$"
```

**Check secrets are set:**
```bash
echo $SLACK_BOT_TOKEN  # Should show xoxb-...
echo $SLACK_APP_TOKEN  # Should show xapp-...
```

### Can't Connect to Kagent

**Single-cluster troubleshooting:**
```bash
# Test endpoint
curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json

# If using port-forward, check it's running
lsof -i :8083

# Restart port-forward if needed
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
```

**Multi-cluster troubleshooting:**
```bash
# Test each endpoint
for url in \
  "http://192.168.1.200:8080" \
  "http://192.168.1.201:8080" \
  "http://192.168.1.202:8080"
do
  echo "Testing $url..."
  curl -s "$url/api/a2a/kagent/k8s-agent/.well-known/agent.json" | jq .name || echo "FAILED"
done
```

**Common issues:**
- **Connection refused**: Service not running or wrong port
- **Connection timeout**: Firewall blocking port
- **404 Not Found**: Wrong namespace or agent name
- **No route to host**: Network/VPN not configured

### Bot Not Responding in Slack

1. **Check bot is running:**
   ```bash
   ps aux | grep slack_bot.py
   ```

2. **Check Slack configuration:**
   - Socket Mode enabled?
   - Event Subscriptions enabled?
   - `app_mention` event subscribed?
   - Bot has correct scopes?

3. **Check logs for errors:**
   ```bash
   tail -f kagent-bot.log
   ```

4. **Verify tokens:**
   ```bash
   # Bot token should start with xoxb-
   echo $SLACK_BOT_TOKEN | grep "^xoxb-"

   # App token should start with xapp-
   echo $SLACK_APP_TOKEN | grep "^xapp-"
   ```

### Cluster Not Detected (Multi-Cluster)

The bot detects these keywords:
- **test**: test, testing, tst
- **dev**: dev, development, develop
- **prod**: prod, production, prd
- **stage**: stage, staging, stg

**Examples that work:**
```
@kagent list pods in test cluster        ✅
@kagent check development namespace      ✅
@kagent show production deployments      ✅
```

**Examples that don't work:**
```
@kagent list pods                        ❌ (uses default cluster)
@kagent check namespaces                 ❌ (uses default cluster)
```

**Add custom aliases:**
```bash
# In .env
KAGENT_TEST_ALIASES=testing,tst,test-cluster,qa,testenv
```

---

## Security Best Practices

### Secrets Management

**✅ DO:**
- Set tokens as environment variables
- Use `chmod 600 .env` to restrict file permissions
- Add `.env` to `.gitignore` (already done)
- Use different tokens for dev/test/prod

**❌ DON'T:**
- Commit `.env` files with real tokens
- Share tokens in Slack or email
- Use production tokens for testing
- Run as root user

### Network Security

**For production:**
- Use VPN for cluster access over internet
- Consider Cloudflare tunnels for secure access
- Configure firewall rules to restrict access
- Use TLS/HTTPS when possible

---

## Monitoring

### Check Bot Status

```bash
# Check if bot is running
ps aux | grep slack_bot.py

# Check resource usage
ps aux | grep slack_bot.py | awk '{print $3, $4}'  # CPU%, Memory%
```

### View Logs

```bash
# Real-time logs
tail -f kagent-bot.log

# Last 100 lines
tail -n 100 kagent-bot.log

# Search for errors
grep -i "error\|failed" kagent-bot.log
```

### Important Log Patterns

**Success:**
```
🔔 Received app_mention
📤 Sending message to Kagent
✅ Message processed
```

**Errors:**
```
❌ Request failed
⏱️ Request timeout
⚠️ JSON-RPC error
```

---

## Next Steps

- **Kubernetes deployment:** See [KUBERNETES.md](KUBERNETES.md)
- **Local development:** See [LOCAL_DEV.md](LOCAL_DEV.md)
- **Secrets management:** See [SECRETS.md](SECRETS.md)
- **Troubleshooting:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Testing:** See [TESTING.md](TESTING.md)

---

## Support

- **Questions?** Open an issue in the GitHub repository
- **Slack configuration:** See [README.md](README.md#slack-app-setup)
- **AgentGateway issues:** Check [Kagent documentation](https://kagent.dev/docs)
