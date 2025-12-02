---
title: Kagent Slack Bot
---

# Kagent Slack Bot

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![Kubernetes](https://img.shields.io/badge/kubernetes-native-326CE5.svg)](https://kubernetes.io/)

> **A secure, production-ready Slack bot that connects your workspace to Kagent's Kubernetes AI agents using the A2A (Agent2Agent) protocol.**

Ask questions about your Kubernetes cluster in natural language directly from Slack. Get instant insights, debug issues, and manage resources through conversational AI.

---

## Table of Contents

- [Features](#features)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Installation](#installation)
  - [Local Development](#local-development)
  - [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration](#configuration)
- [Security](#security)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## Features

✅ **Natural Language Interface** - Ask questions like "@kagent what pods are running in production?"
✅ **Multi-Cluster Routing** - Single bot routes to multiple clusters based on keywords
✅ **Conversational Context** - Maintains conversation history within Slack threads (per cluster)
✅ **A2A Protocol** - Standard Agent2Agent communication with streaming support
✅ **Socket Mode** - No public URLs needed, works behind firewalls
✅ **Cloudflare Access Support** - Optional service token authentication for external access
✅ **Istio Integration** - Native support for Istio ingress gateway
✅ **Production Ready** - Security hardened with proper error handling
✅ **Kubernetes Native** - Designed for cluster deployment with full pod security compliance
✅ **Flexible Deployment** - Run on laptop, server, or in-cluster

---

## Quick Start

### Prerequisites

- **Slack workspace** with admin access to create apps
- **Kagent** installed and running in your Kubernetes cluster
  - 🚀 **New to Kagent?** Follow the [Kagent Getting Started Guide](https://kagent.dev/docs/kagent/getting-started/quickstart) to:
    - Spin up a local kind cluster (if you don't have one)
    - Install Kagent with the default k8s-agent
    - Get running in minutes!
- **Python 3.13+** (for local development) OR **Kubernetes cluster** (for production)
- **Docker** (optional, for building custom images)

### 5-Minute Setup

```bash
# 0. Setup Kagent (if you haven't already)
# Follow: https://kagent.dev/docs/kagent/getting-started/quickstart
# This creates a kind cluster with Kagent and the default k8s-agent

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

### What You Get from Kagent Quickstart

Following the [Kagent Getting Started Guide](https://kagent.dev/docs/kagent/getting-started/quickstart) will set up:

- ✅ **Local kind cluster** (if you don't have one)
- ✅ **Kagent installed** in the `kagent` namespace
- ✅ **Default k8s-agent** ready to answer questions about your cluster
- ✅ **Kagent controller** running on port 8083
- ✅ **A2A endpoint** at `http://localhost:8083/api/a2a/kagent/k8s-agent` (after port-forward)

This Slack bot then connects to that endpoint, enabling you to:
- Ask questions about your cluster from Slack
- Get real-time responses from the k8s-agent
- Maintain conversation context within Slack threads

**Perfect for:** Local development, testing, and learning how Kagent works before deploying to production.

---

## Architecture

```
┌─────────────────────┐
│  Slack (Browser)    │
│  @kagent what ...?  │
└──────────┬──────────┘
           │ WebSocket (Socket Mode - Secure)
           ↓
┌─────────────────────────────┐
│   Kagent Slack Bot          │
│   ┌─────────────────────┐   │
│   │ Event Handler       │   │  ← Receives @mentions
│   │ Thread Manager      │   │  ← Maps Slack threads to contextIds
│   └──────────┬──────────┘   │
│              │               │
│   ┌──────────▼──────────┐   │
│   │ KagentClient        │   │  ← A2A Protocol Implementation
│   │ - JSON-RPC 2.0      │   │
│   │ - SSE Streaming     │   │
│   │ - Context Tracking  │   │
│   └──────────┬──────────┘   │
└──────────────┼──────────────┘
               │ HTTPS POST (SSL Verified)
               │ Content-Type: application/json
               │ Accept: text/event-stream
               ↓
┌───────────────────────────────┐
│  Kagent Controller            │
│  (Port 8083)                  │
│  - Streams SSE events         │
│  - Maintains contextId        │
└──────────────┬────────────────┘
               │ Routes to agent
               ↓
┌───────────────────────────────┐
│  k8s-agent (AI Agent)         │
│  - Processes with context     │
│  - Uses MCP tools             │
└──────────────┬────────────────┘
               │ kubectl commands
               ↓
┌───────────────────────────────┐
│  Kubernetes API               │
│  - Gets resources             │
│  - Fetches logs               │
└───────────────────────────────┘
```

**Key Security Features:**
- WebSocket connection secured via Slack Socket Mode
- HTTPS with SSL verification for Kagent communication
- No public endpoints required (Socket Mode)
- Environment-based credential management
- Input sanitization in logs

---

## Installation

### Local Development

Perfect for testing and development. Full instructions in [LOCAL_DEV.md](LOCAL_DEV.md).

**Prerequisites:**
- Kagent running in your cluster ([setup guide](https://kagent.dev/docs/kagent/getting-started/quickstart))

**Quick Steps:**

```bash
# 1. Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure (copy and edit .env)
cp .env.example .env

# 3. Port-forward Kagent
kubectl port-forward -n kagent svc/kagent-controller 8083:8083 &

# 4. Run
python slack_bot.py
```

### Kubernetes Deployment

Production deployment with full security hardening. Full instructions in [KUBERNETES.md](KUBERNETES.md).

**Quick Steps:**

```bash
# 1. Create Slack credentials secret
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-your-bot-token-here' \
  --from-literal=app-token='xapp-your-app-token-here' \
  --namespace=kagent

# 2. (Optional) Customize namespace/agent in k8s-deployment.yaml
# Edit KAGENT_NAMESPACE and KAGENT_AGENT_NAME values

# 3. Deploy
kubectl apply -f k8s-deployment.yaml

# 4. Verify
kubectl logs -n kagent -l app=kagent-slack-bot -f
```

**Security:** The deployment includes:
- Pod Security Standards (restricted) compliance
- Read-only root filesystem
- Non-root user (UID 1000)
- Dropped all capabilities
- No privilege escalation
- Seccomp runtime default profile
- Resource limits

---

## Configuration

### Environment Variables

The bot supports multiple configuration modes:

#### Option 1: Single Cluster (Simple Setup)

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
KAGENT_A2A_URL=http://localhost:8083/api/a2a/kagent/k8s-agent
```

#### Option 2: Multi-Cluster Routing (Recommended)

Route to different clusters based on keywords in messages:

```bash
# Slack tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Enable multi-cluster routing
ENABLE_MULTI_CLUSTER=true

# Kagent configuration
KAGENT_BASE_URL=http://kagent-controller:8083
KAGENT_NAMESPACE=kagent

# Define clusters
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test

# Agent naming pattern
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
```

This routes messages like:
- `"@kagent list pods on test cluster"` → `k8s-agent-test`
- `"@kagent check dev"` → `k8s-agent-dev`
- `"@kagent show namespaces"` → default cluster (`k8s-agent-test`)

#### Option 3: External Access with Cloudflare (Production)

For exposing through Cloudflare tunnel with authentication:

```bash
# Slack tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Multi-cluster routing
ENABLE_MULTI_CLUSTER=true
KAGENT_BASE_URL=https://kagent.yourdomain.com
KAGENT_NAMESPACE=kagent
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}

# Cloudflare Access service token (optional)
CF_ACCESS_CLIENT_ID=your-client-id
CF_ACCESS_CLIENT_SECRET=your-client-secret
```

**See detailed setup guides:**
- [LAPTOP_SERVER_SETUP.md](LAPTOP_SERVER_SETUP.md) - Run on laptop/Debian server
- [ISTIO_CLOUDFLARE_SETUP.md](ISTIO_CLOUDFLARE_SETUP.md) - Istio + Cloudflare tunnel
- [TALOS_SETUP.md](TALOS_SETUP.md) - Talos Linux specific configuration
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - Common issues and fixes

### Slack App Setup

**Required OAuth Scopes:**
- `app_mentions:read` - Detect @mentions
- `chat:write` - Post messages
- `channels:history` - Read channel history

**Required Settings:**
1. **Socket Mode** - Enabled with `connections:write` scope
2. **Event Subscriptions** - Enabled with `app_mention` event
3. **Request URL** - Leave blank (Socket Mode doesn't need it)

**Detailed setup guide:** See the Configuration section below for step-by-step instructions.

---

## Security

This project follows 2025 security best practices:

### Application Security
- ✅ Environment-based configuration (no hardcoded secrets)
- ✅ Input validation and sanitization
- ✅ SSL/TLS verification enabled
- ✅ Timeout protection (5-minute max request time)
- ✅ Secure random message ID generation (SHA-256)
- ✅ Log injection prevention
- ✅ Minimal dependencies with pinned versions

### Container Security
- ✅ Non-root user (UID/GID 1000)
- ✅ Minimal base image (python:3.13-slim-bookworm)
- ✅ No unnecessary packages
- ✅ Read-only root filesystem compatible
- ✅ Explicit labels for traceability

### Kubernetes Security
- ✅ Pod Security Standards: restricted
- ✅ `allowPrivilegeEscalation: false`
- ✅ `readOnlyRootFilesystem: true`
- ✅ `runAsNonRoot: true`
- ✅ Capabilities dropped: ALL
- ✅ Seccomp profile: RuntimeDefault
- ✅ Service account auto-mount disabled
- ✅ Resource limits defined

**Vulnerability Reporting:** This is an open-source project. Please open a GitHub issue for security concerns.

---

## Usage

### Basic Interaction

```
# Invite the bot to a channel
/invite @kagent

# Ask questions
@kagent list all namespaces
@kagent what pods are running in production?
@kagent show me logs for the first pod
```

### Thread Context

Each Slack thread maintains its own conversation context:

```
Thread 1:
  User: @kagent what namespaces exist?
  Bot: default, kube-system, apps, production
  User: @kagent how many pods in the first one?  ← Remembers "first one" = default
  Bot: 12 pods running in default namespace

Thread 2:
  User: @kagent check the apps namespace        ← Separate context
```

### A2A Protocol Details

The bot implements the [A2A Protocol](https://a2a-protocol.org/latest/specification/) with:

**Request Format (JSON-RPC 2.0):**
```json
{
  "jsonrpc": "2.0",
  "method": "message/stream",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "your question"}],
      "messageId": "msg-abc123",
      "contextId": "thread-context-id"
    }
  },
  "id": 1
}
```

**Response Format (Server-Sent Events):**
```
event: task_status_update
data: {"result":{"status":{"state":"submitted"}}}

event: task_status_update
data: {"result":{"status":{"message":{"role":"agent","parts":[{"text":"response"}]}}}}

event: task_status_update
data: {"result":{"final":true,"status":{"state":"completed"}}}
```

---

## Troubleshooting

### Bot Not Responding to Mentions

**Most common issue:** Event Subscriptions not configured correctly

1. Go to https://api.slack.com/apps → Your App
2. **Event Subscriptions** → Verify:
   - Toggle is ON
   - `app_mention` is in "Subscribe to bot events"
   - **Request URL is BLANK** (Socket Mode doesn't use it)
3. Click **"Reinstall to Workspace"**
4. Restart the bot

### Can't Connect to Kagent

```bash
# Test endpoint is reachable
curl http://localhost:8083/api/a2a/kagent/k8s-agent/.well-known/agent.json

# Should return agent metadata (not 404)
# If 404, verify namespace and agent name are correct
```

### Kubernetes Pod Not Starting

```bash
# Check pod status
kubectl get pods -n kagent -l app=kagent-slack-bot

# View logs
kubectl logs -n kagent -l app=kagent-slack-bot

# Common issues:
# - Missing secret: create slack-credentials secret first
# - Wrong namespace: ensure Kagent is in the correct namespace
# - Network policies: verify pod can reach kagent-controller service
```

### Read-Only Filesystem Errors

The bot runs with `readOnlyRootFilesystem: true`. Temporary files are written to mounted volumes:
- `/tmp` - general temporary files
- `/home/kagent/.cache` - Python cache

These are automatically configured in the Kubernetes deployment.

**More help:**
- [LOCAL_DEV.md](LOCAL_DEV.md#troubleshooting) - Local development issues
- [KUBERNETES.md](KUBERNETES.md#troubleshooting) - Production deployment issues

---

## Contributing

Contributions are welcome! This project is designed to be clean, maintainable, and secure.

### Current Features
- ✅ Conversation context within threads
- ✅ SSE streaming support
- ✅ Clean class-based architecture
- ✅ Comprehensive error handling
- ✅ Security hardened
- ✅ Production ready

### Areas for Contribution
- Long-term conversation memory (Redis/database)
- Multi-agent support (switch agents mid-conversation)
- Slash commands (`/kagent ask ...`)
- Interactive buttons and forms
- Metrics and observability (Prometheus/Grafana)
- Unit and integration tests
- Performance optimizations

### Development Setup

```bash
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run locally with port-forward
kubectl port-forward -n kagent svc/kagent-controller 8083:8083 &
python slack_bot.py
```

---

## Project Structure

```
kagent-slack-bot/
├── slack_bot.py              # Main application (~320 lines)
│   ├── KagentClient          # A2A protocol client
│   ├── SSE stream parser     # Server-Sent Events handling
│   └── Slack event handlers  # @mention handling & threading
├── requirements.txt          # Python dependencies (pinned versions)
├── Dockerfile                # Multi-platform container image (security hardened)
├── k8s-deployment.yaml       # Kubernetes deployment (pod security: restricted)
├── build.sh                  # Multi-arch Docker build script
├── .env.example              # Environment variable template
├── .dockerignore             # Docker build exclusions
├── .gitignore                # Git exclusions
├── LICENSE                   # MIT License
├── README.md                 # This file (overview)
├── LOCAL_DEV.md              # Local development guide
├── KUBERNETES.md             # Production deployment guide
└── QUICKSTART.md             # 5-minute quick reference
```

---

## License

MIT License - Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so.

See [LICENSE](LICENSE) file for full details.

---

## Resources

### Kagent
- **Kagent Getting Started:** https://kagent.dev/docs/kagent/getting-started/quickstart (Setup kind cluster + Kagent)
- **Kagent Documentation:** https://kagent.dev/docs
- **Kagent Architecture:** https://kagent.dev/docs/kagent/architecture

### Protocols & Standards
- **A2A Protocol Specification:** https://a2a-protocol.org/latest/specification/
- **Kubernetes Pod Security Standards:** https://kubernetes.io/docs/concepts/security/pod-security-standards/

### Slack Development
- **Slack Bolt for Python:** https://slack.dev/bolt-python/
- **Slack Socket Mode:** https://api.slack.com/apis/connections/socket
- **Slack API Documentation:** https://api.slack.com/docs

---

## Acknowledgments

Built with:
- **Google's A2A (Agent2Agent) Protocol** - Standard for agent communication
- **Slack's Bolt Framework** for Python - Modern Slack app development
- **Kagent** - Kubernetes AI agent platform
- **Python 3.13** - Latest stable Python with security improvements

---

## Support

- 📖 **Documentation:** [LOCAL_DEV.md](LOCAL_DEV.md) | [KUBERNETES.md](KUBERNETES.md) | [QUICKSTART.md](QUICKSTART.md)
- 🐛 **Issues:** [GitHub Issues](https://github.com/your-org/kagent-slack-bot/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/your-org/kagent-slack-bot/discussions)

---

**Made with ❤️ for the Kubernetes community**
