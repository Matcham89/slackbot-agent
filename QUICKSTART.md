# Kagent Slack Bot - Quick Start Guide

Get your Kagent Slack bot running in 5 minutes!

## Choose Your Deployment Method

### Method 1: Single Bot Per Cluster (**Simplest**)
- One bot per cluster (e.g., @kagent-test, @kagent-prod)
- Bot runs inside the cluster
- Direct A2A connection (port 8083)
- **[Full guide: KUBERNETES.md](KUBERNETES.md)**

### Method 2: Multi-Cluster via AgentGateway
- ONE bot for all clusters (@kagent)
- Detect cluster keywords in messages
- Requires AgentGateway (port 8080)
- **[Full guide: LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md)**

---

## Quick Start - Method 1 (Single Bot Per Cluster)

### Prerequisites
- Kagent installed in your cluster
- kubectl configured
- Slack workspace admin access

### 3-Step Deployment

**1. Create Slack credentials secret:**
```bash
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-your-bot-token' \
  --from-literal=app-token='xapp-your-app-token' \
  --namespace=kagent
```

**2. Deploy the bot:**
```bash
kubectl apply -f k8s-deployment-single-cluster.yaml
```

**3. Verify:**
```bash
kubectl logs -n kagent -l app=kagent-slack-bot -f
```

**Expected output:**
```
✅ Slack app initialized
⚡️ Kagent Slack Bot is running!
```

### Test in Slack
```
/invite @kagent
@kagent list all namespaces
```

---

## Quick Start - Method 2 (Multi-Cluster)

### Prerequisites
- Python 3.13+ installed
- AgentGateway deployed on each cluster
- Network access to cluster IPs

### 4-Step Setup

**1. Clone and install:**
```bash
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Configure `.env`:**
```bash
cp .env.example .env
nano .env
```

Set:
```bash
ENABLE_MULTI_CLUSTER=true
KAGENT_CLUSTERS=test,dev
KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
```

**3. Run the bot:**
```bash
python slack_bot.py
```

**4. Test in Slack:**
```
/invite @kagent
@kagent list pods in test cluster
@kagent check dev namespaces
```

---

## Getting Slack Tokens

1. Go to https://api.slack.com/apps
2. **Create New App** → From scratch
3. Name it "kagent" and select your workspace
4. **Socket Mode**:
   - Enable Socket Mode
   - Create app-level token with `connections:write` scope
   - Copy the token (starts with `xapp-`)
5. **OAuth & Permissions**:
   - Add Bot Token Scopes:
     - `app_mentions:read`
     - `chat:write`
     - `channels:history`
   - Install App to Workspace
   - Copy Bot User OAuth Token (starts with `xoxb-`)
6. **Event Subscriptions**:
   - Enable Events
   - Subscribe to `app_mention` bot event

---

## Configuration Comparison

| Feature | Method 1 | Method 2 |
|---------|----------|----------|
| Slack bots | One per cluster | One bot total |
| Deployment | In-cluster (Kubernetes) | Laptop/server/K8s |
| Port | 8083 (direct A2A) | 8080 (AgentGateway) |
| Setup time | 3 minutes | 5 minutes |
| AgentGateway | Not required | Required |
| Cluster switching | Switch bots | Use keywords in message |

---

## Next Steps

- **Method 1 full guide**: [KUBERNETES.md](KUBERNETES.md)
- **Method 2 full guide**: [LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md)
- **Local development**: [LOCAL_DEV.md](LOCAL_DEV.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Main README**: [README.md](README.md)

---

## Troubleshooting

### Bot not responding?
1. Check logs: `kubectl logs -n kagent -l app=kagent-slack-bot`
2. Verify Slack app settings (Socket Mode, Event Subscriptions)
3. Check secret is created: `kubectl get secret slack-credentials -n kagent`

### Can't connect to Kagent?
```bash
# Method 1 (port 8083)
curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json

# Method 2 (port 8080)
curl http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**More help**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
