# Secrets Management Guide

This guide explains how to properly handle secrets (tokens, credentials) for the Kagent Slack Bot.

## Security Principles

🔒 **NEVER commit secrets to git**
🔒 **NEVER put secrets in .env files that might be shared**
🔒 **ALWAYS use environment variables for secrets**
🔒 **ALWAYS use Kubernetes Secrets in production**

---

## Required Secrets

### SLACK_BOT_TOKEN
- **Format**: `xoxb-...`
- **Source**: Slack App → OAuth & Permissions → Bot User OAuth Token
- **Used for**: Posting messages to Slack

### SLACK_APP_TOKEN
- **Format**: `xapp-...`
- **Source**: Slack App → Basic Information → App-Level Tokens
- **Scope**: `connections:write`
- **Used for**: Socket Mode connection

---

## Optional Secrets

### Cloudflare Access (if using Cloudflare tunnel)

**CF_ACCESS_CLIENT_ID** and **CF_ACCESS_CLIENT_SECRET**
- Used for authenticating with Cloudflare Access
- Both must be set together

---

## Local Development

For local development, export secrets as environment variables:

```bash
# Set secrets in your shell (not in .env file!)
export SLACK_BOT_TOKEN="xoxb-your-actual-bot-token"
export SLACK_APP_TOKEN="xapp-your-actual-app-token"

# Optional: Cloudflare Access
export CF_ACCESS_CLIENT_ID="your-client-id"
export CF_ACCESS_CLIENT_SECRET="your-client-secret"

# Now run the bot
python slack_bot.py
```

### Option 1: Export in your shell

Add to your `~/.bashrc`, `~/.zshrc`, or `~/.bash_profile`:

```bash
# Kagent Slack Bot secrets (NEVER commit this file)
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
```

Then reload: `source ~/.bashrc`

### Option 2: Use a secrets file (outside git)

Create a file **outside the repository** (e.g., `~/kagent-secrets.sh`):

```bash
#!/bin/bash
# Kagent Slack Bot Secrets
export SLACK_BOT_TOKEN="xoxb-..."
export SLACK_APP_TOKEN="xapp-..."
```

Make it executable and source it:

```bash
chmod +x ~/kagent-secrets.sh
source ~/kagent-secrets.sh
python slack_bot.py
```

### Option 3: One-time export per session

```bash
# Temporary - only for this shell session
export SLACK_BOT_TOKEN="xoxb-..." SLACK_APP_TOKEN="xapp-..."
python slack_bot.py
```

---

## Production Deployment (Kubernetes)

### Method 1: Create Secret from Literals

```bash
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-your-actual-bot-token' \
  --from-literal=app-token='xapp-your-actual-app-token' \
  --namespace=kagent
```

### Method 2: Create Secret from File

Create a file `secrets.yaml` (DO NOT commit this file):

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: slack-credentials
  namespace: kagent
type: Opaque
stringData:
  bot-token: xoxb-your-actual-bot-token
  app-token: xapp-your-actual-app-token
```

Apply it:

```bash
kubectl apply -f secrets.yaml
# Delete the file immediately after
rm secrets.yaml
```

### Method 3: Create Secret from Env File

Create a temporary file `slack.env` (DO NOT commit):

```
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

Create secret:

```bash
kubectl create secret generic slack-credentials \
  --from-env-file=slack.env \
  --namespace=kagent

# Delete the file immediately
rm slack.env
```

### Verify Secret

```bash
# Check secret exists (values are base64 encoded)
kubectl get secret slack-credentials -n kagent

# View secret (will show base64 encoded values)
kubectl get secret slack-credentials -n kagent -o yaml

# Decode to verify (only do this in secure environment)
kubectl get secret slack-credentials -n kagent -o jsonpath='{.data.bot-token}' | base64 -d
```

---

## Using Secrets in Deployment

The deployment YAML automatically loads secrets as environment variables:

```yaml
env:
  # Secrets (from Kubernetes Secret)
  - name: SLACK_BOT_TOKEN
    valueFrom:
      secretKeyRef:
        name: slack-credentials
        key: bot-token
  - name: SLACK_APP_TOKEN
    valueFrom:
      secretKeyRef:
        name: slack-credentials
        key: app-token
```

---

## Rotating Secrets

### Kubernetes Deployment

1. **Update the secret:**

```bash
kubectl create secret generic slack-credentials \
  --from-literal=bot-token='xoxb-new-token' \
  --from-literal=app-token='xapp-new-token' \
  --namespace=kagent \
  --dry-run=client -o yaml | kubectl apply -f -
```

2. **Restart the bot to pick up new secrets:**

```bash
kubectl rollout restart deployment/kagent-slack-bot -n kagent
```

### Local Development

Just update your environment variables and restart the bot:

```bash
export SLACK_BOT_TOKEN="xoxb-new-token"
export SLACK_APP_TOKEN="xapp-new-token"
python slack_bot.py
```

---

## Troubleshooting

### Bot not connecting to Slack

1. **Verify secrets are set:**

```bash
# Local development
echo $SLACK_BOT_TOKEN
echo $SLACK_APP_TOKEN

# Kubernetes
kubectl get secret slack-credentials -n kagent
```

2. **Check token format:**

```bash
# Bot token should start with xoxb-
echo $SLACK_BOT_TOKEN | grep "^xoxb-"

# App token should start with xapp-
echo $SLACK_APP_TOKEN | grep "^xapp-"
```

3. **Validate tokens in Slack:**

- Go to https://api.slack.com/apps
- Select your app
- OAuth & Permissions → Check Bot User OAuth Token
- Basic Information → App-Level Tokens → Check token

### Secrets not loading in Kubernetes

1. **Check secret exists in correct namespace:**

```bash
kubectl get secret slack-credentials -n kagent
```

2. **Check deployment references correct secret:**

```bash
kubectl get deployment kagent-slack-bot -n kagent -o yaml | grep -A 10 "secretKeyRef"
```

3. **Check pod environment:**

```bash
kubectl exec -n kagent deployment/kagent-slack-bot -- env | grep SLACK
```

---

## Best Practices

### ✅ DO

- Use Kubernetes Secrets in production
- Use environment variables for local development
- Rotate secrets regularly (every 90 days)
- Use different tokens for dev/test/prod
- Delete secret files immediately after creating Kubernetes secrets
- Use `kubectl create secret` from command line (doesn't leave files)
- Add `.env` to `.gitignore` (already done)

### ❌ DON'T

- Commit .env files with actual tokens
- Share tokens in Slack or email
- Put tokens in ConfigMaps (use Secrets instead)
- Log or print token values
- Store tokens in source code
- Use production tokens for development

---

## Getting Slack Tokens

1. **Go to https://api.slack.com/apps**

2. **Create New App** (or select existing)
   - Click "Create New App"
   - Choose "From scratch"
   - Name: `kagent` (or your preferred name)
   - Select your workspace

3. **Enable Socket Mode**
   - Go to "Socket Mode"
   - Enable Socket Mode
   - Click "Generate Token and Scopes"
   - Token Name: `kagent-websocket`
   - Scope: `connections:write`
   - Generate
   - **Copy the token** (starts with `xapp-`) → This is your `SLACK_APP_TOKEN`

4. **Add OAuth Scopes**
   - Go to "OAuth & Permissions"
   - Scroll to "Scopes" → "Bot Token Scopes"
   - Add these scopes:
     - `app_mentions:read`
     - `chat:write`
     - `channels:history`

5. **Install App to Workspace**
   - Go to "OAuth & Permissions"
   - Click "Install to Workspace"
   - Authorize
   - **Copy "Bot User OAuth Token"** (starts with `xoxb-`) → This is your `SLACK_BOT_TOKEN`

6. **Enable Event Subscriptions**
   - Go to "Event Subscriptions"
   - Enable Events
   - Subscribe to bot events: `app_mention`
   - Save Changes

7. **Reinstall if needed**
   - If you make changes, click "Reinstall to Workspace"

---

## Security Checklist

Before deploying to production:

- [ ] Secrets are stored in Kubernetes Secrets (not ConfigMaps or env vars)
- [ ] No secrets in .env files
- [ ] No secrets committed to git
- [ ] Tokens validated in Slack app settings
- [ ] Different tokens used for dev/test/prod
- [ ] Secret rotation plan in place
- [ ] Access to secrets limited to necessary personnel

---

## Additional Resources

- [Kubernetes Secrets Documentation](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Slack API: Tokens](https://api.slack.com/authentication/token-types)
- [Slack API: Best Practices](https://api.slack.com/authentication/best-practices)
