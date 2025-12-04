# Laptop/Server Deployment Guide - Method 2: Multi-Cluster via AgentGateway

Deploy ONE Kagent Slack bot on a laptop or server that routes to multiple clusters via AgentGateway.

## When to Use This Method

- You want a **single Slack bot** for all clusters (@kagent)
- Users specify cluster keywords (test, dev, prod) in messages
- Central management from one bot instance
- AgentGateway is deployed and accessible on each cluster

## Architecture

```
Slack → Bot (laptop/server) → AgentGateway (port 8080) → Kagent Controller → k8s-agent → Kubernetes API
                                     ↓
                            Routes to test, dev, or prod cluster
```

The bot runs on a middleman machine with network access to all AgentGateway endpoints.

---

## Prerequisites

- **Python 3.13+** installed
- **Network access** to all cluster AgentGateway endpoints (port 8080)
  - Test cluster: `192.168.1.200:8080`
  - Dev cluster: `192.168.1.201:8080`
- **AgentGateway** deployed on each cluster
- **Slack workspace** admin access (to create/configure bot)

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
# Copy example config
cp .env.example .env

# Edit .env with your configuration
nano .env
```

**Update .env for multi-cluster setup:**

```bash
# Slack credentials
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Enable multi-cluster mode
ENABLE_MULTI_CLUSTER=true

# Kagent namespace (same across all clusters)
KAGENT_NAMESPACE=kagent

# Define clusters (comma-separated)
KAGENT_CLUSTERS=test,dev

# Default cluster when no keyword detected
KAGENT_DEFAULT_CLUSTER=test

# Agent name pattern (same agent name on all clusters)
KAGENT_AGENT_PATTERN=k8s-agent

# AgentGateway endpoints (port 8080)
KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
# KAGENT_PROD_BASE_URL=http://192.168.1.202:8080
```

**Get Slack tokens:**
- Bot token (xoxb-...): Slack App → OAuth & Permissions → Bot User OAuth Token
- App token (xapp-...): Slack App → Basic Information → App-Level Tokens

### 3. Test Connection

Test that you can reach AgentGateway endpoints:

```bash
# Test test cluster
curl http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json

# Test dev cluster
curl http://192.168.1.201:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**Expected output:** JSON with agent metadata (not 404 or connection refused).

### 4. Run the Bot

```bash
# Activate virtual environment
source venv/bin/activate

# Run bot
python slack_bot.py
```

**Expected output:**
```
✅ Slack app initialized
🚀 Starting Kagent Slack Bot...
🌐 Multi-cluster routing mode enabled
   Using pattern-based routing: k8s-agent
   Kagent: http://192.168.1.200:8080
   Clusters: test, dev
   Default cluster: test
⚡️ Kagent Slack Bot is running!
⚡️ Bolt app is running!
```

### 5. Test in Slack

```
# Invite bot to a channel
/invite @kagent

# Test routing to different clusters
@kagent list namespaces in test cluster
@kagent what pods are running in dev?
@kagent show deployments  ← Uses default cluster (test)
```

The bot should detect cluster keywords and route accordingly!

---

## Running as a Systemd Service (Linux)

For production deployment on a Linux server, run as a systemd service.

### 1. Create Service File

```bash
sudo nano /etc/systemd/system/kagent-slack-bot.service
```

**Add the following:**

```ini
[Unit]
Description=Kagent Slack Bot (Multi-Cluster)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/kagent-slack-bot
EnvironmentFile=/home/your-username/kagent-slack-bot/.env
ExecStart=/home/your-username/kagent-slack-bot/venv/bin/python slack_bot.py
Restart=always
RestartSec=10

# Security hardening
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

**Update:**
- Replace `your-username` with your actual username
- Update paths to match your installation directory

### 2. Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable kagent-slack-bot

# Start service
sudo systemctl start kagent-slack-bot

# Check status
sudo systemctl status kagent-slack-bot
```

### 3. View Logs

```bash
# Follow logs in real-time
sudo journalctl -u kagent-slack-bot -f

# View last 100 lines
sudo journalctl -u kagent-slack-bot -n 100

# View logs since boot
sudo journalctl -u kagent-slack-bot -b
```

### 4. Manage Service

```bash
# Restart service
sudo systemctl restart kagent-slack-bot

# Stop service
sudo systemctl stop kagent-slack-bot

# Disable service
sudo systemctl disable kagent-slack-bot
```

---

## Running on macOS/Windows

For non-Linux systems, use a terminal session or process manager.

### macOS

**Option 1: Terminal (Development)**
```bash
# Run in terminal
source venv/bin/activate
python slack_bot.py
```

**Option 2: Background Process**
```bash
# Run in background
nohup python slack_bot.py > kagent-bot.log 2>&1 &

# View logs
tail -f kagent-bot.log

# Stop bot
pkill -f slack_bot.py
```

### Windows

**Option 1: Command Prompt (Development)**
```cmd
# Activate environment
venv\Scripts\activate

# Run bot
python slack_bot.py
```

**Option 2: Windows Service (Advanced)**
Use tools like [NSSM](https://nssm.cc/) to run as a Windows service.

---

## Configuration

### Adding More Clusters

Edit `.env` to add more clusters:

```bash
# Add production cluster
KAGENT_CLUSTERS=test,dev,prod
KAGENT_PROD_BASE_URL=http://192.168.1.202:8080
```

**Restart the bot:**
```bash
# If running manually
Ctrl+C, then: python slack_bot.py

# If running as systemd service
sudo systemctl restart kagent-slack-bot
```

### Changing Default Cluster

```bash
# Set dev as default instead of test
KAGENT_DEFAULT_CLUSTER=dev
```

Messages without cluster keywords will route to dev.

### Network Troubleshooting

If bot can't reach AgentGateway endpoints:

**Check connectivity:**
```bash
# Ping cluster IPs
ping 192.168.1.200
ping 192.168.1.201

# Test HTTP connection
curl -v http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**Common issues:**
- **Connection refused**: AgentGateway not running or wrong port
- **Connection timeout**: Firewall blocking port 8080
- **DNS resolution failed**: Using hostname instead of IP, DNS not configured

**Solutions:**
- Verify AgentGateway is running: `kubectl get pods -n kagent`
- Check firewall rules allow port 8080
- Use VPN if clusters are on private network
- Use IP addresses instead of hostnames if DNS not available

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

# Restart bot
# If systemd:
sudo systemctl restart kagent-slack-bot

# If running manually:
Ctrl+C, then: python slack_bot.py
```

### Update Slack Tokens

Edit `.env` with new tokens:

```bash
SLACK_BOT_TOKEN=xoxb-new-token
SLACK_APP_TOKEN=xapp-new-token
```

**Restart bot** to apply changes.

---

## Monitoring

### Check Bot Status

```bash
# If running as systemd service
sudo systemctl status kagent-slack-bot

# If running manually
ps aux | grep slack_bot.py
```

### View Logs

**Systemd service:**
```bash
sudo journalctl -u kagent-slack-bot -f
```

**Manual/background process:**
```bash
tail -f kagent-bot.log
```

**Look for:**
```
🔔 Received app_mention event
   Detected cluster: test
🆕 Starting new conversation for cluster: test
📊 Processed 5 events from stream
💬 Found agent response
```

---

## Troubleshooting

### Bot Not Starting

**Check Python version:**
```bash
python --version  # Should be 3.13+
```

**Check dependencies:**
```bash
pip install -r requirements.txt
```

**Check .env file:**
```bash
cat .env | grep -v "^#"  # View active config
```

### Bot Not Responding in Slack

1. Check bot is running: `systemctl status kagent-slack-bot`
2. Check Slack tokens are correct in `.env`
3. Verify Slack app configuration (Socket Mode, Event Subscriptions)
4. Check logs for errors: `journalctl -u kagent-slack-bot -n 50`

### Can't Connect to AgentGateway

**Test endpoints:**
```bash
# Test each cluster
for ip in 192.168.1.200 192.168.1.201; do
  echo "Testing $ip..."
  curl -s "http://$ip:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json" | jq .name || echo "Failed to connect to $ip"
done
```

**Common fixes:**
- Check VPN connection if using VPN
- Verify firewall rules allow outbound to port 8080
- Confirm AgentGateway is running on clusters

### Cluster Keyword Not Detected

The bot looks for these keywords in messages:
- `test`, `testing` → routes to test cluster
- `dev`, `development` → routes to dev cluster
- `prod`, `production` → routes to prod cluster

**Examples:**
- ✅ `@kagent list pods in test cluster`
- ✅ `@kagent check dev namespace`
- ✅ `@kagent show test deployments`
- ❌ `@kagent list pods` → uses default cluster

---

## Security Considerations

### Protect .env File

```bash
# Restrict file permissions
chmod 600 .env

# Never commit .env to git
echo ".env" >> .gitignore
```

### Network Security

- Use VPN for accessing cluster endpoints over internet
- Consider using Cloudflare tunnels for secure access
- Firewall rules to restrict access to AgentGateway ports

### Run as Non-Root User

Always run the bot as a non-privileged user, never as root.

---

## Deployment Comparison

| Feature | Method 1 (Single Bot Per Cluster) | Method 2 (Multi-Cluster) |
|---------|-----------------------------------|--------------------------|
| **Slack bots** | One per cluster (@kagent-test, @kagent-prod) | One bot for all (@kagent) |
| **Deployment location** | Inside each cluster | Laptop/server/any cluster |
| **Port** | 8083 (direct A2A) | 8080 (AgentGateway) |
| **Setup complexity** | Simple | Moderate |
| **Network requirements** | In-cluster only | Access to all cluster IPs |
| **AgentGateway** | Not required | Required on each cluster |
| **Cluster switching** | Switch bots in Slack | Use keywords in message |

---

## Next Steps

- **Kubernetes deployment**: See [k8s-deployment-multi-cluster.yaml](k8s-deployment-multi-cluster.yaml) to run this setup in Kubernetes
- **Single bot per cluster**: See [KUBERNETES.md](KUBERNETES.md) for Method 1
- **Local development**: See [LOCAL_DEV.md](LOCAL_DEV.md)
- **Troubleshooting**: See [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

---

## Support

- **Questions?** Open an issue in the GitHub repository
- **AgentGateway issues?** Check Kagent documentation
- **Slack configuration help?** See [README.md](README.md#slack-app-setup)
