# Talos Linux Cluster Setup

## Your Network
- VIP: 192.168.1.180
- Control Plane: 192.168.1.181
- Worker: 192.168.1.191
- Debian Server: Same network (192.168.1.x)

## Setup Instructions

### 1. Expose Kagent Controller via NodePort

```bash
# Check current service type
kubectl get svc -n kagent kagent-controller

# If it's ClusterIP, change to NodePort
kubectl patch svc kagent-controller -n kagent -p '{"spec":{"type":"NodePort"}}'

# Get the NodePort (will be in range 30000-32767)
NODE_PORT=$(kubectl get svc -n kagent kagent-controller -o jsonpath='{.spec.ports[0].nodePort}')
echo "Kagent NodePort: $NODE_PORT"

# Example output: 30123
```

### 2. Test Connectivity

```bash
# Test from Debian server using VIP
curl http://192.168.1.180:$NODE_PORT/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# OR test using control plane IP
curl http://192.168.1.181:$NODE_PORT/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# Should return JSON (agent metadata)
```

### 3. Configure Bot `.env`

```bash
# Slack tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Multi-cluster routing
ENABLE_MULTI_CLUSTER=true

# Kagent configuration (using VIP + NodePort)
KAGENT_BASE_URL=http://192.168.1.180:30123  # Replace 30123 with your NodePort
KAGENT_NAMESPACE=kagent

# Clusters
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test

# Agent pattern
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
```

### 4. Test Configuration

```bash
# Test each agent endpoint
curl http://192.168.1.180:30123/api/a2a/kagent/k8s-agent-test/.well-known/agent.json
curl http://192.168.1.180:30123/api/a2a/kagent/k8s-agent-dev/.well-known/agent.json
curl http://192.168.1.180:30123/api/a2a/kagent/k8s-agent-prod/.well-known/agent.json

# All should return JSON (not 404)
```

### 5. Run the Bot

```bash
cd /path/to/slackbot-agent
source venv/bin/activate
python slack_bot.py
```

## Talos-Specific Considerations

### Firewall Rules

Talos Linux has a built-in firewall. Ensure NodePort range is accessible:

```yaml
# In your Talos machine config
machine:
  network:
    firewall:
      rules:
        - ingress:
            protocol: tcp
            ports: [30000-32767]  # NodePort range
```

### High Availability with VIP

Using the VIP (192.168.1.180) is recommended because:
- ✅ Traffic automatically routes to healthy nodes
- ✅ Survives node failures
- ✅ No need to update config if nodes change

**Recommended `.env`:**
```bash
KAGENT_BASE_URL=http://192.168.1.180:30123
```

### Alternative: Direct Node Access

If VIP is not available or you want to bypass it:

```bash
# Use control plane directly
KAGENT_BASE_URL=http://192.168.1.181:30123

# OR use worker node
KAGENT_BASE_URL=http://192.168.1.191:30123
```

## Troubleshooting

### Connection Refused

```bash
# Check if Kagent is running
kubectl get pods -n kagent

# Check service endpoints
kubectl get endpoints -n kagent kagent-controller

# Verify NodePort
kubectl get svc -n kagent kagent-controller
```

### Timeout

```bash
# Check firewall on Debian server
sudo iptables -L -n | grep 30123

# Check connectivity
ping 192.168.1.180
telnet 192.168.1.180 30123
```

### Agent Not Found (404)

```bash
# List all agents in Kagent
kubectl get agents -n kagent

# Verify agent names match your pattern
# Should see: k8s-agent-test, k8s-agent-dev, k8s-agent-prod
```

## Production Setup with systemd

Once working, set up as a service:

```bash
# Edit service file
nano kagent-slack-bot.service

# Update WorkingDirectory and ExecStart paths
# Then:
sudo cp kagent-slack-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kagent-slack-bot
sudo systemctl start kagent-slack-bot

# Check status
sudo systemctl status kagent-slack-bot
sudo journalctl -u kagent-slack-bot -f
```

## Quick Commands

```bash
# Get NodePort
kubectl get svc -n kagent kagent-controller -o jsonpath='{.spec.ports[0].nodePort}'

# Test endpoint
NODE_PORT=$(kubectl get svc -n kagent kagent-controller -o jsonpath='{.spec.ports[0].nodePort}')
curl http://192.168.1.180:$NODE_PORT/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# Update .env
echo "KAGENT_BASE_URL=http://192.168.1.180:$NODE_PORT" >> .env

# Run bot
python slack_bot.py
```
