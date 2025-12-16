# Local Development Guide

Run the Kagent Slack bot locally on your machine for development and testing.

## Prerequisites

- **Python 3.13+** installed
- **Slack App** configured (see [README.md](README.md#slack-app-setup))
- **Kagent** running in Kubernetes cluster
- **kubectl** access to your cluster

## Quick Start

### 1. Port-Forward Kagent

Open a terminal and keep this running:

```bash
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
```

You should see:
```
Forwarding from 127.0.0.1:8083 -> 8083
Forwarding from [::1]:8083 -> 8083
```

**Keep this terminal open while developing.**

### 2. Setup Python Environment

```bash
# Clone repository
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot

# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # On macOS/Linux
# OR
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Copy example config
cp .env.example .env
```

Edit `.env` with your tokens:

```bash
# Get these from https://api.slack.com/apps
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Single-cluster mode (for local dev)
ENABLE_MULTI_CLUSTER=false

# Local port-forward endpoint
KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent
```

**Important:** Update `kagent` and `k8s-agent` to match your setup:
- `kagent` = namespace where Kagent is deployed
- `k8s-agent` = name of your agent

### 4. Run the Bot

```bash
python slack_bot.py
```

You should see:
```
✅ Slack app initialized
🚀 Starting Kagent Slack Bot...
   Kagent: http://localhost:8083
   Agent: kagent/k8s-agent
⚡ Bot is running! Waiting for @mentions...
⚡ Bolt app is running!
```

### 5. Test in Slack

1. **Invite bot to channel:**
   ```
   /invite @kagent
   ```

2. **Test conversation context:**
   ```
   @kagent list all namespaces
   @kagent how many pods in the first one?
   ```

   The bot should remember "the first one" refers to the first namespace!

3. **Watch terminal logs:**
   ```
   🔔 Received app_mention
      Thread: 1761860108.627629
   🆕 Starting new conversation
   📤 Sending message to Kagent
   📊 Processed 7 events from stream
   💬 Found agent response
   ✅ Message processed

   # Second message in same thread:
   🔔 Received app_mention
   🔄 Using existing contextId: 7d5e0706-...
   📊 Processed 5 events from stream
   ✅ Message processed
   ```

## Development Workflow

### Making Changes

1. Edit `slack_bot.py`
2. Stop bot (Ctrl+C - graceful shutdown)
3. Restart bot (`python slack_bot.py`)
4. Test in Slack

**Note:** When you stop with Ctrl+C, you'll see:
```
🛑 Shutting down gracefully...
   Bot stopped
```

### Debugging

**Enable debug logging:**

Edit `slack_bot.py` and change:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Changed from INFO
    format='%(asctime)s - %(levelname)s - %(message)s'
)
```

**Test A2A endpoint directly:**
```bash
curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

Should return agent info (not 404).

## Troubleshooting

### Port-forward disconnects

If you see "connection refused" errors:

```bash
# Check port-forward is running
lsof -i :8083

# If not, restart it
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
```

### Bot not receiving events

1. **Check Socket Mode is enabled:**
   - Go to https://api.slack.com/apps
   - Select your app → Socket Mode → Toggle should be ON

2. **Check Event Subscriptions:**
   - Event Subscriptions → Toggle should be ON
   - `app_mention` should be in "Subscribe to bot events"
   - Click "Reinstall to Workspace" if you made changes

3. **Check tokens:**
   ```bash
   # View .env file
   grep SLACK .env
   # Tokens should start with xoxb- and xapp-
   ```

### Module not found errors

```bash
# Make sure venv is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Wrong namespace/agent

If you get 404 errors, update `.env` with correct values:

```bash
KAGENT_A2A_URL=http://localhost:8083/api/a2a/<NAMESPACE>/<AGENT-NAME>
```

## Clean Up

When done developing:

```bash
# Stop the bot (Ctrl+C in terminal)
# Stop port-forward (Ctrl+C in port-forward terminal)
# Deactivate virtual environment
deactivate
```

## Next Steps

- **Production deployment:** See [KUBERNETES.md](KUBERNETES.md) or [LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md)
- **Slack app setup:** See [README.md](README.md#slack-app-setup)
- **Troubleshooting:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
