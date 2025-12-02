# Kagent Slack Bot - Laptop/Server Deployment Guide

## Overview

Deploy a **single central bot** on your laptop or Debian server that routes Slack messages to multiple Kagent controllers across different Kubernetes clusters.

```
┌──────────────────────────────────────────┐
│  Your Laptop / Debian Server             │
│  ┌────────────────────────────────────┐  │
│  │  @kagent Slack Bot (ONE instance)  │  │
│  │  - Detects cluster keywords        │  │
│  │  - Routes to correct endpoint      │  │
│  │  - Maintains per-cluster contexts  │  │
│  └─────────────┬──────────────────────┘  │
└────────────────┼─────────────────────────┘
                 │
    ┌────────────┼────────────┐
    ↓            ↓            ↓
┌────────┐  ┌────────┐  ┌────────┐
│ Test   │  │ Dev    │  │ Prod   │
│ Kagent │  │ Kagent │  │ Kagent │
└────────┘  └────────┘  └────────┘
```

---

## Prerequisites

- Python 3.13+ installed
- Network access to all Kagent controller endpoints
- Slack workspace admin access (to create/configure bot)

---

## Quick Start

### 1. Clone and Setup

```bash
# Clone the repository
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your configuration
nano .env  # or vim, code, etc.
```

**Example `.env` for multi-cluster routing:**

```bash
# Slack Credentials
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Enable Multi-Cluster Routing
ENABLE_MULTI_CLUSTER=true

# Kagent Controller (single endpoint)
KAGENT_BASE_URL=http://kagent-controller:8083
KAGENT_NAMESPACE=kagent

# Define Available Clusters
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test

# Agent Pattern (generates: k8s-agent-test, k8s-agent-dev, k8s-agent-prod)
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}

# This will route to:
# - test: http://kagent-controller:8083/api/a2a/kagent/k8s-agent-test
# - dev:  http://kagent-controller:8083/api/a2a/kagent/k8s-agent-dev
# - prod: http://kagent-controller:8083/api/a2a/kagent/k8s-agent-prod
```

### 3. Network Access Setup

#### Option A: Port Forwarding (Laptop/Local Development)

Forward the Kagent controller from the cluster where your agents are running:

```bash
# Port-forward the Kagent controller
kubectl config use-context your-cluster-context
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
```

Update `.env` to use localhost:
```bash
KAGENT_BASE_URL=http://localhost:8083
KAGENT_NAMESPACE=kagent
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
```

#### Option B: VPN/Direct Network Access (Server)

If your server has direct network access to the Kagent controller:

```bash
# Use the Kagent controller hostname or IP
KAGENT_BASE_URL=http://kagent-controller.example.com:8083
KAGENT_NAMESPACE=kagent
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
```

### 4. Test Connection

Verify each agent endpoint is reachable:

```bash
# Test agent
curl http://localhost:8083/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# Dev agent
curl http://localhost:8083/api/a2a/kagent/k8s-agent-dev/.well-known/agent.json

# Prod agent
curl http://localhost:8083/api/a2a/kagent/k8s-agent-prod/.well-known/agent.json
```

Each should return agent metadata JSON (not 404). If you get 404, verify:
- The agent names match your configuration
- The agents exist in your Kagent deployment

### 5. Run the Bot

```bash
# Activate virtual environment if not already
source venv/bin/activate

# Run the bot
python slack_bot.py
```

You should see:
```
🚀 Initializing Slack bot...
🌐 Multi-cluster routing mode enabled
🔧 Kagent client initialized (multi-cluster routing mode)
   Clusters: test, dev, prod
   Default: test
   Using pattern-based routing: k8s-agent-{cluster}
   test: http://localhost:8083/api/a2a/kagent/k8s-agent-test/
   dev: http://localhost:8083/api/a2a/kagent/k8s-agent-dev/
   prod: http://localhost:8083/api/a2a/kagent/k8s-agent-prod/
✅ Slack app initialized
⚡ Bot is running! Waiting for @mentions...
```

---

## Systemd Service (Debian Server)

For production deployment on a Debian server:

### 1. Install as Service

```bash
# Edit the service file
nano kagent-slack-bot.service

# Update these paths:
# - User/Group: your username
# - WorkingDirectory: /home/youruser/slackbot-agent
# - EnvironmentFile: /home/youruser/slackbot-agent/.env
# - ExecStart: /home/youruser/slackbot-agent/venv/bin/python ...

# Copy to systemd
sudo cp kagent-slack-bot.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable service (start on boot)
sudo systemctl enable kagent-slack-bot

# Start service
sudo systemctl start kagent-slack-bot

# Check status
sudo systemctl status kagent-slack-bot

# View logs
sudo journalctl -u kagent-slack-bot -f
```

### 2. Service Management

```bash
# Start
sudo systemctl start kagent-slack-bot

# Stop
sudo systemctl stop kagent-slack-bot

# Restart
sudo systemctl restart kagent-slack-bot

# Status
sudo systemctl status kagent-slack-bot

# Logs (last 50 lines)
sudo journalctl -u kagent-slack-bot -n 50

# Follow logs live
sudo journalctl -u kagent-slack-bot -f
```

---

## Usage Examples

### Cluster-Specific Queries

```
User: @kagent how many pods on test cluster?
Bot: [queries test Kagent] There are 12 pods running in test cluster

User: @kagent what about dev?
Bot: [queries dev Kagent] There are 8 pods running in dev cluster

User: @kagent show me production namespaces
Bot: [queries prod Kagent] Production has: default, apps, monitoring
```

### Default Cluster (No Keyword)

```
User: @kagent list all namespaces
Bot: [queries default cluster (test)] default, kube-system, kagent, apps
```

### Thread Context Awareness

```
Thread 1:
  User: @kagent pods in test
  Bot: [test cluster response]
  User: @kagent show logs for the first one
  Bot: [remembers test context, queries test cluster]

  User: @kagent now check dev cluster
  Bot: [switches to dev cluster]
  User: @kagent same thing, show logs
  Bot: [remembers dev context within this thread]
```

---

## Troubleshooting

### Bot Not Responding

1. **Check logs:**
   ```bash
   sudo journalctl -u kagent-slack-bot -n 100
   ```

2. **Verify Slack tokens are valid:**
   - Go to https://api.slack.com/apps
   - Check bot token and app token haven't expired

3. **Test Slack connection:**
   - Bot should log: `⚡ Bot is running! Waiting for @mentions...`

### Cannot Reach Cluster Endpoints

1. **Test connectivity:**
   ```bash
   curl http://your-kagent-endpoint/.well-known/agent.json
   ```

2. **Check port-forwards are active:**
   ```bash
   ps aux | grep port-forward
   ```

3. **Verify DNS/hostname resolution:**
   ```bash
   ping kagent-controller.example.com
   ```

### Wrong Cluster Responding

1. **Check cluster detection:**
   - Look for log line: `🎯 Detected cluster: test`
   - Try more explicit keywords: "test cluster" instead of just "test"

2. **Verify endpoint URLs are different:**
   ```bash
   grep KAGENT_ .env
   ```

### Service Won't Start

1. **Check file permissions:**
   ```bash
   ls -la /path/to/slackbot-agent
   chmod +x slack_bot.py
   ```

2. **Verify Python path:**
   ```bash
   /path/to/slackbot-agent/venv/bin/python --version
   ```

3. **Check environment file:**
   ```bash
   cat .env | grep -v "^#" | grep .
   ```

---

## Network Requirements

The server/laptop running the bot needs:

- **Outbound HTTPS** to Slack (api.slack.com, wss://wss-*.slack.com)
- **HTTP access** to the Kagent controller endpoint
- **Port availability** for port-forwarding (if using that method)

### Firewall Rules (Example)

```bash
# Allow outbound HTTPS to Slack
sudo ufw allow out 443/tcp

# Allow outbound to Kagent controller (adjust IP)
sudo ufw allow out to 10.0.1.10 port 8083
```

---

## Security Best Practices

1. **Protect .env file:**
   ```bash
   chmod 600 .env
   ```

2. **Use service account (don't run as root):**
   ```bash
   sudo useradd -r -s /bin/false kagent-bot
   sudo chown -R kagent-bot:kagent-bot /path/to/slackbot-agent
   ```

3. **Restrict network access:**
   - Only allow bot to reach Kagent endpoints
   - No inbound connections needed (Socket Mode)

4. **Monitor logs for suspicious activity:**
   ```bash
   sudo journalctl -u kagent-slack-bot | grep ERROR
   ```

---

## Updating the Bot

```bash
# Pull latest changes
cd /path/to/slackbot-agent
git pull

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt

# Restart service
sudo systemctl restart kagent-slack-bot

# Verify
sudo systemctl status kagent-slack-bot
```

---

## Architecture Benefits

✅ **Single Point of Entry** - One @kagent bot for all clusters
✅ **Central Management** - Update one bot instance, affects all clusters
✅ **Cluster-Aware Context** - Maintains separate conversations per cluster
✅ **Network Flexibility** - Works with port-forward, VPN, or direct access
✅ **No Cross-Cluster Conflicts** - Only one bot responds based on keyword
✅ **Easy to Scale** - Add new clusters by adding env vars

---

## Support

- **Logs**: `sudo journalctl -u kagent-slack-bot -f`
- **Slack API**: https://api.slack.com/apps
- **Kagent Docs**: https://kagent.dev/docs

Happy multi-cluster routing! 🚀
