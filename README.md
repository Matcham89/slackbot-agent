# Kagent Slack Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-native-326CE5.svg)](https://kubernetes.io/)

> **A secure Slack bot that connects your workspace to Kagent's Kubernetes AI agents using the A2A (Agent2Agent) protocol.**

Ask questions about your Kubernetes cluster in natural language directly from Slack. Get instant insights, debug issues, and manage resources through conversational AI.

---

## 🎉 What's New in v2.0

**Token Management & Context Control:**
- 🔍 **Token Tracking** - Real-time monitoring of conversation token usage
- ⚠️ **Intelligent Limits** - Automatic detection and prevention of token limit errors
- 🔄 **Context Commands** - `@kagent reset context`, `@kagent context info`
- 📊 **Usage Indicators** - Visual feedback when approaching token limits

**Improved Multi-Cluster Support:**
- 🎯 **Smarter Routing** - Enhanced keyword detection with alias support
- 🏷️ **Custom Aliases** - Configure cluster aliases (e.g., "production" → "prod")
- 🔗 **Per-Cluster Contexts** - Isolated conversation history for each cluster

**Better Configuration:**
- 🔐 **Secrets Separation** - Clear distinction between config and sensitive data
- 📝 **Structured Config** - New `config.py` module for type-safe configuration
- 🛡️ **Security First** - Secrets never in .env files, only environment variables

**Developer Experience:**
- ✅ **Unit Tests** - Comprehensive test coverage for multi-cluster features
- 📚 **Better Docs** - New [SECRETS.md](SECRETS.md) and [TESTING.md](TESTING.md) guides
- 🐛 **Improved Errors** - User-friendly error messages with actionable solutions

---

## Features

✅ **Natural Language Interface** - Ask questions like "@kagent what pods are running in production?"
✅ **Two Deployment Methods** - Single bot per cluster OR one bot for multiple clusters
✅ **Multi-Cluster Routing** - Detect cluster keywords (test, dev, prod) in messages with alias support
✅ **Conversational Context** - Maintains conversation history within Slack threads
✅ **Token Management** - Automatic tracking and warnings for conversation size limits
✅ **Interactive Commands** - `help`, `reset context`, `context info` for better control
✅ **A2A Protocol** - Standard Agent2Agent communication with streaming support
✅ **Socket Mode** - No public URLs needed, works behind firewalls
✅ **Production Ready** - Security hardened with proper error handling
✅ **Kubernetes Native** - Full pod security compliance
✅ **Well Tested** - Comprehensive unit tests for core functionality

---

## Quick Start

### Prerequisites

- **Slack workspace** with admin access to create apps
- **Kagent** installed and running in your Kubernetes cluster(s)
  - New to Kagent? Follow the [Kagent Getting Started Guide](https://kagent.dev/docs/kagent/getting-started/quickstart)
- **Python 3.13+** (for local development) OR **Kubernetes cluster** (for production)
- **Docker** (optional, for building custom images)

### 5-Minute Local Development Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot

# 2. Port-forward Kagent (for local testing)
kubectl port-forward -n kagent svc/kagent-controller 8083:8083 &

# 3. Configure environment
cp .env.example .env
# Edit .env with your Slack tokens (see Configuration section below)

# 4. Run locally
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python slack_bot.py
```

**See [QUICKSTART.md](QUICKSTART.md) for detailed 5-minute setup guide.**

---

## Deployment Options

### Where to Deploy

**Option 1: Kubernetes Deployment**
- Bot runs as a pod inside your cluster
- Production-ready with proper security standards
- See [KUBERNETES.md](KUBERNETES.md)

**Option 2: Local Deployment (Laptop/Server)**
- Bot runs directly via Python on your machine
- Great for development and testing
- See [LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md)

### Cluster Configuration

**Both deployment options support:**

**Single-Cluster Mode:**
- Connect to ONE Kubernetes cluster
- Direct A2A connection (port 8083)
- Simple configuration

**Multi-Cluster Mode (Optional):**
- Connect to MULTIPLE clusters from one bot
- Users specify cluster in messages (e.g., "test", "dev", "prod")
- Requires AgentGateway on each cluster (port 8080)

---

## Quick Deploy Examples

### Kubernetes Deployment (Single-Cluster)

```bash
# Create secret with Slack tokens
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-your-bot-token' \
  --from-literal=app-token='xapp-your-app-token' \
  --namespace=kagent

# Deploy
kubectl apply -f k8s-deployment-single-cluster.yaml
```

**Architecture:**
```
Slack → Bot (in cluster) → Kagent Controller :8083 → k8s-agent → Kubernetes API
```

---

### Local Deployment (Single-Cluster)

```bash
# Port-forward Kagent
kubectl port-forward -n kagent svc/kagent-controller 8083:8083 &

# Configure
cp .env.example .env
# Set: ENABLE_MULTI_CLUSTER=false
# Set: KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent

# Set secrets
export SLACK_BOT_TOKEN="xoxb-your-token"
export SLACK_APP_TOKEN="xapp-your-token"

# Run
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python slack_bot.py
```

**Architecture:**
```
Slack → Bot (laptop) → Kagent Controller :8083 → k8s-agent → Kubernetes API
```

---

### Local Deployment (Multi-Cluster)

```bash
# Configure
cp .env.example .env
# Set: ENABLE_MULTI_CLUSTER=true
# Set: KAGENT_CLUSTERS=test,dev,prod
# Set: KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
# Set: KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
# Set: KAGENT_PROD_BASE_URL=http://192.168.1.202:8080

# Set secrets
export SLACK_BOT_TOKEN="xoxb-your-token"
export SLACK_APP_TOKEN="xapp-your-token"

# Run
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python slack_bot.py
```

**Architecture:**
```
Slack → Bot (laptop) → AgentGateway :8080 → Kagent Controller → k8s-agent
                            ↓
                   Routes to test, dev, or prod cluster
```

**Usage:**
```
@kagent list pods in test cluster  → Routes to test
@kagent check dev namespaces       → Routes to dev
@kagent show deployments           → Uses default cluster
```

---

## Configuration

### Environment Variables

**Secrets (MUST be environment variables, NOT in .env):**
```bash
export SLACK_BOT_TOKEN="xoxb-your-bot-token"
export SLACK_APP_TOKEN="xapp-your-app-token"
```

See [SECRETS.md](SECRETS.md) for detailed secrets management guide.

**Single-Cluster Mode:**

```bash
# Deployment mode
ENABLE_MULTI_CLUSTER=false

# Option 1: Full URL (recommended)
KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent

# Option 2: Separate components
# KAGENT_BASE_URL=http://localhost:8083
# KAGENT_NAMESPACE=kagent
# KAGENT_AGENT_NAME=k8s-agent
```

**Multi-Cluster Mode (Optional):**

```bash
# Deployment mode
ENABLE_MULTI_CLUSTER=true

# Kagent configuration
KAGENT_NAMESPACE=kagent
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test
KAGENT_AGENT_PATTERN=k8s-agent

# AgentGateway endpoints (port 8080)
KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
KAGENT_DEV_BASE_URL=http://192.168.1.201:8080
KAGENT_PROD_BASE_URL=http://192.168.1.202:8080

# Optional: Custom aliases
KAGENT_TEST_ALIASES=testing,tst,test-cluster
KAGENT_DEV_ALIASES=development,develop,dev-cluster
KAGENT_PROD_ALIASES=production,prd,prod-cluster
```

**Operational Settings (Optional):**

```bash
REQUEST_TIMEOUT=300         # Request timeout in seconds (default: 300)
MAX_CONTEXT_TOKENS=300000   # Max tokens before warning (default: 300k)
LOG_LEVEL=INFO              # Log level: DEBUG, INFO, WARNING, ERROR
```

### Slack App Setup

**Required OAuth Scopes:**
- `app_mentions:read` - Detect @mentions
- `chat:write` - Post messages
- `channels:history` - Read channel history

**Required Settings:**
1. **Socket Mode** - Enabled with `connections:write` scope
2. **Event Subscriptions** - Enabled with `app_mention` event
3. **Request URL** - Leave blank (Socket Mode doesn't need it)

**Get your tokens:**
1. Go to https://api.slack.com/apps → Create New App
2. **OAuth & Permissions** → Copy Bot User OAuth Token (xoxb-...)
3. **Basic Information** → App-Level Tokens → Create token with `connections:write` scope (xapp-...)

---

## Architecture

### Single-Cluster Mode

```
┌─────────────────────┐
│  Slack (Browser)    │
│  @kagent what ...?  │
└──────────┬──────────┘
           │ WebSocket (Socket Mode)
           ↓
┌─────────────────────────────┐
│   Kagent Slack Bot          │
│   (local or in-cluster)     │
│   - Event Handler           │
│   - A2A Client              │
└──────────┬──────────────────┘
           │ HTTPS POST (port 8083)
           ↓
┌───────────────────────────────┐
│  Kagent Controller            │
│  - Direct A2A endpoint        │
└──────────┬────────────────────┘
           │
           ↓
┌───────────────────────────────┐
│  k8s-agent (AI Agent)         │
│  - kubectl via MCP tools      │
└───────────────────────────────┘
```

### Multi-Cluster Mode (Optional)

```
┌─────────────────────┐
│  Slack (Browser)    │
│  @kagent test ...   │
└──────────┬──────────┘
           │ WebSocket (Socket Mode)
           ↓
┌─────────────────────────────┐
│   Kagent Slack Bot          │
│   (local or in-cluster)     │
│   - Detects "test" keyword  │
│   - Multi-cluster router    │
└──────────┬──────────────────┘
           │ HTTPS POST (port 8080)
           ↓
┌───────────────────────────────┐
│  AgentGateway (Test Cluster)  │
│  IP: 192.168.1.200:8080       │
└──────────┬────────────────────┘
           │ Forwards to
           ↓
┌───────────────────────────────┐
│  Kagent Controller            │
│  - Processes request          │
└──────────┬────────────────────┘
           │
           ↓
┌───────────────────────────────┐
│  k8s-agent (AI Agent)         │
│  - kubectl via MCP tools      │
└───────────────────────────────┘
```

---

## Usage

### Basic Commands

```
# Invite the bot to a channel
/invite @kagent

# Get help
@kagent help

# Context management (v2.0+)
@kagent context info      # Show token usage
@kagent reset context     # Clear conversation history
```

### Single-Cluster Mode

```
@kagent list all namespaces
@kagent what pods are running?
@kagent show me logs for the first pod
@kagent describe the deployment
```

### Multi-Cluster Mode (Optional)

```
# Specify cluster in message
@kagent list pods in test cluster
@kagent check dev namespace status
@kagent show prod deployments

# Without keyword, uses default cluster
@kagent list namespaces  ← Routes to default cluster
```

### Thread Context

Each Slack thread maintains its own conversation context:

```
Thread 1:
  User: @kagent what namespaces exist?
  Bot: default, kube-system, kagent
  User: @kagent how many pods in the first one?  ← Remembers "first one" = default
  Bot: 12 pods running in default namespace
```

---

## Security

This project follows 2025 security best practices:

### Application Security
- ✅ Environment-based configuration (no hardcoded secrets)
- ✅ SSL/TLS verification enabled
- ✅ Timeout protection (5-minute max)
- ✅ Secure message ID generation (SHA-256)
- ✅ Log injection prevention
- ✅ Minimal dependencies with pinned versions

### Kubernetes Security
- ✅ Pod Security Standards: restricted
- ✅ `allowPrivilegeEscalation: false`
- ✅ `readOnlyRootFilesystem: true`
- ✅ `runAsNonRoot: true`
- ✅ Capabilities dropped: ALL
- ✅ Seccomp profile: RuntimeDefault
- ✅ Service account auto-mount disabled
- ✅ Resource limits defined

---

## Troubleshooting

### Bot Not Responding to Mentions

1. Verify Event Subscriptions in Slack app settings
2. Check `app_mention` is subscribed
3. Reinstall app to workspace
4. Check bot logs: `kubectl logs -n kagent -l app=kagent-slack-bot`

### Can't Connect to Kagent

**Method 1 (Direct A2A):**
```bash
# Test endpoint
curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**Method 2 (AgentGateway):**
```bash
# Test endpoint
curl http://192.168.1.200:8080/api/a2a/kagent/k8s-agent/.well-known/agent.json
```

**See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more help.**

---

## Documentation

### Getting Started
- **[QUICKSTART.md](QUICKSTART.md)** - 5-minute setup guide
- **[KUBERNETES.md](KUBERNETES.md)** - Method 1: Single bot per cluster deployment
- **[LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md)** - Method 2: Multi-cluster middleman deployment
- **[LOCAL_DEV.md](LOCAL_DEV.md)** - Local development guide

### Configuration & Security
- **[SECRETS.md](SECRETS.md)** - Secrets management and best practices
- **[.env.example](.env.example)** - Configuration template (no secrets!)

### Troubleshooting & Testing
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** - Common issues and fixes (including token limits!)
- **[TESTING.md](TESTING.md)** - Testing guide and running unit tests

---

### Running Tests

```bash
python3 -m venv venv-test
source venv-test/bin/activate
pip install -r requirements.txt
python -m unittest test_bot_functions -v
```

See [TESTING.md](TESTING.md) for detailed testing guide.

---

## License

MIT License - Copyright (c) 2025

See [LICENSE](LICENSE) file for full details.

---

## Resources

### Kagent
- **Kagent Getting Started:** https://kagent.dev/docs/kagent/getting-started/quickstart
- **Kagent Documentation:** https://kagent.dev/docs

### Protocols & Standards
- **A2A Protocol Specification:** https://a2a-protocol.org/latest/specification/

### Slack Development
- **Slack Bolt for Python:** https://slack.dev/bolt-python/
- **Slack Socket Mode:** https://api.slack.com/apis/connections/socket

---

**Made with ❤️ for the Kubernetes community**
