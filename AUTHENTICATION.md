# Authentication Configuration Guide

## Overview

The Kagent Slack Bot supports optional authentication via Cloudflare Access service tokens for securing external access to your Kagent endpoints.

---

## When Do You Need Authentication?

| Scenario | Authentication Required? | Method |
|----------|-------------------------|--------|
| Bot on same network as cluster | ❌ No | Internal IP/hostname |
| Bot via VPN to cluster | ❌ No | Internal access |
| Bot accessing via Cloudflare tunnel (public) | ✅ Yes (Recommended) | Service Token |
| Local development | ❌ No | Port-forward |

---

## Configuration Options

### Option 1: No Authentication (Internal Access)

**Best for:**
- Bot on same network as cluster
- Development/testing
- VPN-connected access

**Configuration:**
```bash
# .env
KAGENT_BASE_URL=http://192.168.1.200:8083
# No CF_ACCESS credentials needed
```

---

### Option 2: Cloudflare Access Service Token

**Best for:**
- Bot accessing Kagent via Cloudflare tunnel
- External/public access
- Production security

**Configuration:**
```bash
# .env
KAGENT_BASE_URL=https://kagent.yourdomain.com
CF_ACCESS_CLIENT_ID=your-client-id
CF_ACCESS_CLIENT_SECRET=your-client-secret
```

---

## Setup Cloudflare Access Service Token

### Step 1: Create Service Token

1. Go to **Cloudflare Zero Trust Dashboard**: https://one.dash.cloudflare.com
2. Navigate to **Access** → **Service Authentication** → **Service Tokens**
3. Click **Create Service Token**
4. Enter details:
   - **Name**: `kagent-slack-bot`
   - **Duration**: Choose expiry (or "Does not expire")
5. Click **Generate token**
6. **IMPORTANT**: Copy both the **Client ID** and **Client Secret** immediately
   - You won't be able to see the Client Secret again!

### Step 2: Create Access Application

1. Go to **Access** → **Applications**
2. Click **Add an application**
3. Choose **Self-hosted**
4. Configure Application:
   - **Application name**: `Kagent API`
   - **Session duration**: Leave default
   - **Application domain**:
     - **Subdomain**: `kagent`
     - **Domain**: Select your domain from dropdown
5. Click **Next**

### Step 3: Add Policy

1. **Policy name**: `Service Token Only`
2. **Action**: `Service Auth`
3. **Configure rules**:
   - Click **Add include**
   - Select **Service Token**
   - Choose `kagent-slack-bot` from the list
4. Click **Next** → **Add application**

### Step 4: Update Bot Configuration

Add the credentials to your `.env` file:

```bash
CF_ACCESS_CLIENT_ID=abc123def456...
CF_ACCESS_CLIENT_SECRET=xyz789abc123...
```

### Step 5: Test

```bash
# Test with credentials
curl -H "CF-Access-Client-Id: abc123def456..." \
     -H "CF-Access-Client-Secret: xyz789abc123..." \
     https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# Should return JSON (not 403 Forbidden)
```

### Step 6: Run Bot

```bash
# The bot automatically reads CF_ACCESS credentials from .env
python slack_bot.py
```

---

## How It Works

### Without Cloudflare Access

```
Slack Bot → https://kagent.yourdomain.com → Kagent Controller
            (Anyone with URL can access)
```

### With Cloudflare Access

```
Slack Bot → (sends service token) → Cloudflare Access
            (validates token)      → Kagent Controller
                                    ✓ Authorized
```

**The bot automatically:**
1. Reads `CF_ACCESS_CLIENT_ID` and `CF_ACCESS_CLIENT_SECRET` from environment
2. Adds these as HTTP headers: `CF-Access-Client-Id` and `CF-Access-Client-Secret`
3. Cloudflare validates before allowing access

---

## Code Implementation

The bot automatically handles Cloudflare Access headers:

```python
# In slack_bot.py (lines 218-223)
# Add Cloudflare Access service token headers if configured
cf_client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
cf_client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
if cf_client_id and cf_client_secret:
    headers["CF-Access-Client-Id"] = cf_client_id
    headers["CF-Access-Client-Secret"] = cf_client_secret
```

No code changes needed - just set the environment variables!

---

## Troubleshooting

### 403 Forbidden Error

**Cause:** Cloudflare Access is blocking the request

**Solutions:**

1. **Verify service token is active:**
   ```bash
   # Cloudflare Dashboard → Access → Service Tokens
   # Check "kagent-slack-bot" is not expired
   ```

2. **Check credentials in .env:**
   ```bash
   grep CF_ACCESS .env
   # Should show both CLIENT_ID and CLIENT_SECRET
   ```

3. **Test manually with curl:**
   ```bash
   curl -H "CF-Access-Client-Id: your-id" \
        -H "CF-Access-Client-Secret: your-secret" \
        https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-test/.well-known/agent.json
   ```

4. **Verify Access policy:**
   - Cloudflare → Access → Applications → Kagent API
   - Check policy includes the service token

### Token Not Being Sent

**Check bot logs:**
```bash
# Look for this in logs (won't show secrets, just confirms they're set):
# ✓ Cloudflare Access credentials configured
```

**Verify environment variables are loaded:**
```python
# Quick test
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('ID:', 'SET' if os.getenv('CF_ACCESS_CLIENT_ID') else 'NOT SET')
print('Secret:', 'SET' if os.getenv('CF_ACCESS_CLIENT_SECRET') else 'NOT SET')
"
```

### Cloudflare Access Page Shown

**Cause:** Service token not being accepted

**Fix:**
- Ensure policy action is **Service Auth** (not "Allow" or "Deny")
- Service token must be in the **Include** rule (not "Require")

---

## Security Best Practices

### 1. Rotate Tokens Regularly

Create a new service token every 90 days:
1. Create new token with different name (e.g., `kagent-slack-bot-2025-Q2`)
2. Update .env with new credentials
3. Test bot works
4. Delete old token

### 2. Restrict Token Scope

Create separate tokens for different environments:
- `kagent-slack-bot-prod` - Production
- `kagent-slack-bot-dev` - Development

### 3. Monitor Token Usage

Check Cloudflare Access logs:
- **Access** → **Logs** → **Access requests**
- Look for `kagent.yourdomain.com` requests
- Verify service token authentication is working

### 4. Secure .env File

```bash
# Protect credentials file
chmod 600 .env

# Never commit to git
echo ".env" >> .gitignore
```

---

## Comparison: Service Token vs User Authentication

| Feature | Service Token | User Auth (OAuth) |
|---------|---------------|-------------------|
| **Use Case** | Machine-to-machine | Human users |
| **Expiry** | Configurable (or never) | Session-based |
| **Setup** | Simple (2 values) | Complex (OAuth flow) |
| **Bot Access** | ✅ Perfect | ❌ Not suitable |
| **Rotation** | Manual | Automatic |

**For Slack bot → Use Service Token**

---

## Example Configurations

### Development (No Auth)

```bash
SLACK_BOT_TOKEN=xoxb-dev-token
SLACK_APP_TOKEN=xapp-dev-token
KAGENT_BASE_URL=http://localhost:8083
KAGENT_NAMESPACE=kagent
ENABLE_MULTI_CLUSTER=true
KAGENT_CLUSTERS=test,dev
KAGENT_DEFAULT_CLUSTER=test
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
```

### Production (With Cloudflare Access)

```bash
SLACK_BOT_TOKEN=xoxb-prod-token
SLACK_APP_TOKEN=xapp-prod-token
KAGENT_BASE_URL=https://kagent.yourdomain.com
KAGENT_NAMESPACE=kagent
ENABLE_MULTI_CLUSTER=true
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}

# Cloudflare Access
CF_ACCESS_CLIENT_ID=abc123def456...
CF_ACCESS_CLIENT_SECRET=xyz789abc123...
```

---

## Resources

- **Cloudflare Access Docs**: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/
- **Zero Trust Dashboard**: https://one.dash.cloudflare.com
- **Service Token Creation**: https://developers.cloudflare.com/cloudflare-one/identity/service-tokens/

---

## Summary

✅ **Optional** - Only needed for external access via Cloudflare
✅ **Automatic** - Bot handles headers once env vars are set
✅ **Secure** - Service tokens never expire unless configured
✅ **Simple** - Just 2 environment variables

**Start without auth, add it later if needed!**
