# Istio + MetalLB + Cloudflare Tunnel Setup

## Your Infrastructure
- Talos Linux cluster (192.168.1.180-191)
- Istio Ingress Gateway
- MetalLB for LoadBalancer IPs
- Cloudflare Tunnel for external access

## Architecture

```
Cloudflare Tunnel
       ↓
kagent.yourdomain.com (HTTPS)
       ↓
Istio Ingress Gateway (MetalLB IP)
       ↓
Kagent Controller Service
       ↓
k8s-agent-test, k8s-agent-dev, k8s-agent-prod
```

---

## Step 1: Expose Kagent via Istio Gateway

### 1.1 Create Gateway Resource

```yaml
# kagent-gateway.yaml
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: kagent-gateway
  namespace: kagent
spec:
  selector:
    istio: ingressgateway  # Use Istio's default gateway
  servers:
  - port:
      number: 80
      name: http
      protocol: HTTP
    hosts:
    - "kagent.yourdomain.com"  # Replace with your domain
    # Optional: Add TLS redirect
    tls:
      httpsRedirect: true
  - port:
      number: 443
      name: https
      protocol: HTTPS
    hosts:
    - "kagent.yourdomain.com"
    tls:
      mode: SIMPLE
      credentialName: kagent-tls  # Create this secret with your cert
```

### 1.2 Create VirtualService

```yaml
# kagent-virtualservice.yaml
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: kagent-routes
  namespace: kagent
spec:
  hosts:
  - "kagent.yourdomain.com"
  gateways:
  - kagent-gateway
  http:
  - match:
    - uri:
        prefix: "/api/a2a/"
    route:
    - destination:
        host: kagent-controller.kagent.svc.cluster.local
        port:
          number: 8083
```

### 1.3 Apply Configuration

```bash
kubectl apply -f kagent-gateway.yaml
kubectl apply -f kagent-virtualservice.yaml

# Verify
kubectl get gateway -n kagent
kubectl get virtualservice -n kagent
```

---

## Step 2: Configure Cloudflare Tunnel

### 2.1 Get Istio Ingress Gateway IP

```bash
# Get the MetalLB-assigned IP for Istio ingress
kubectl get svc -n istio-system istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# Example output: 192.168.1.200
```

### 2.2 Configure Cloudflare Tunnel

**In your Cloudflare tunnel config (config.yml):**

```yaml
tunnel: <your-tunnel-id>
credentials-file: /etc/cloudflared/credentials.json

ingress:
  # Route kagent.yourdomain.com to Istio ingress
  - hostname: kagent.yourdomain.com
    service: http://192.168.1.200:80  # Istio ingress gateway IP
    originRequest:
      noTLSVerify: false

  # Default rule (required)
  - service: http_status:404
```

### 2.3 Update DNS in Cloudflare

1. Go to Cloudflare Dashboard → DNS
2. Add CNAME record:
   - **Name:** `kagent`
   - **Target:** `<your-tunnel-id>.cfargotunnel.com`
   - **Proxy status:** Proxied (orange cloud)

---

## Step 3: Test Connectivity

```bash
# Test from anywhere (through Cloudflare)
curl https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# Should return JSON (agent metadata)
```

---

## Step 4: Configure Bot `.env`

**On your Debian server:**

```bash
# Slack tokens
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Multi-cluster routing
ENABLE_MULTI_CLUSTER=true

# Kagent configuration (using Cloudflare tunnel domain)
KAGENT_BASE_URL=https://kagent.yourdomain.com  # ← Use HTTPS with your domain
KAGENT_NAMESPACE=kagent

# Clusters
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test

# Agent pattern
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
```

---

## Benefits of This Setup

✅ **Secure**: HTTPS with Cloudflare SSL
✅ **Clean URLs**: `https://kagent.yourdomain.com` instead of IPs
✅ **External Access**: Bot can run anywhere, not just local network
✅ **DDoS Protection**: Cloudflare's DDoS protection included
✅ **Centralized**: One domain for all agent access
✅ **Production-Grade**: Proper ingress controller pattern

---

## Alternative: Internal-Only Setup

If you want the bot to stay internal (not through Cloudflare):

### Option A: Direct MetalLB IP

```bash
# Get Istio ingress IP
ISTIO_IP=$(kubectl get svc -n istio-system istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

# Update .env to use IP directly
KAGENT_BASE_URL=http://$ISTIO_IP
```

### Option B: Local DNS

```bash
# Add to /etc/hosts on Debian server
echo "192.168.1.200 kagent.local" | sudo tee -a /etc/hosts

# Update .env
KAGENT_BASE_URL=http://kagent.local
```

---

## Complete Setup Commands

```bash
# 1. Create Istio Gateway and VirtualService
cat <<EOF | kubectl apply -f -
apiVersion: networking.istio.io/v1beta1
kind: Gateway
metadata:
  name: kagent-gateway
  namespace: kagent
spec:
  selector:
    istio: ingressgateway
  servers:
  - port:
      number: 80
      name: http
      protocol: HTTP
    hosts:
    - "kagent.yourdomain.com"
---
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: kagent-routes
  namespace: kagent
spec:
  hosts:
  - "kagent.yourdomain.com"
  gateways:
  - kagent-gateway
  http:
  - match:
    - uri:
        prefix: "/api/a2a/"
    route:
    - destination:
        host: kagent-controller.kagent.svc.cluster.local
        port:
          number: 8083
EOF

# 2. Get Istio ingress IP (for Cloudflare tunnel config)
kubectl get svc -n istio-system istio-ingressgateway -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

# 3. Test once Cloudflare tunnel is configured
curl https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# 4. Update .env on Debian server
cd /path/to/slackbot-agent
cat > .env <<EOF
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_APP_TOKEN=xapp-your-token
ENABLE_MULTI_CLUSTER=true
KAGENT_BASE_URL=https://kagent.yourdomain.com
KAGENT_NAMESPACE=kagent
KAGENT_CLUSTERS=test,dev,prod
KAGENT_DEFAULT_CLUSTER=test
KAGENT_AGENT_PATTERN=k8s-agent-{cluster}
EOF

# 5. Run bot
source venv/bin/activate
python slack_bot.py
```

---

## Troubleshooting

### Istio Gateway Not Working

```bash
# Check gateway status
kubectl get gateway -n kagent kagent-gateway
kubectl describe gateway -n kagent kagent-gateway

# Check VirtualService
kubectl get virtualservice -n kagent
kubectl describe virtualservice -n kagent kagent-routes

# Check Istio ingress logs
kubectl logs -n istio-system -l app=istio-ingressgateway --tail=50
```

### Cloudflare Tunnel Issues

```bash
# Check tunnel status
cloudflared tunnel info <tunnel-name>

# Check tunnel logs
journalctl -u cloudflared -f

# Test internal connectivity first
curl http://192.168.1.200/api/a2a/kagent/k8s-agent-test/.well-known/agent.json
```

### SSL/TLS Errors

```bash
# Create TLS secret for Istio (if using HTTPS internally)
kubectl create secret tls kagent-tls \
  --cert=path/to/cert.pem \
  --key=path/to/key.pem \
  -n kagent

# Or use cert-manager for automatic certs
```

---

## Security Considerations

### 1. Authentication (Recommended)

Add authentication to Kagent access:

```yaml
# Add to VirtualService
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: kagent-routes
  namespace: kagent
spec:
  hosts:
  - "kagent.yourdomain.com"
  gateways:
  - kagent-gateway
  http:
  - match:
    - uri:
        prefix: "/api/a2a/"
    headers:
      request:
        add:
          X-Forwarded-Proto: https
    route:
    - destination:
        host: kagent-controller.kagent.svc.cluster.local
        port:
          number: 8083
```

### 2. Rate Limiting

```yaml
# Istio rate limiting
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: kagent-ratelimit
  namespace: kagent
spec:
  host: kagent-controller.kagent.svc.cluster.local
  trafficPolicy:
    connectionPool:
      http:
        maxRequestsPerConnection: 100
        http1MaxPendingRequests: 50
```

### 3. Access Logs

```bash
# Enable Istio access logs
kubectl edit configmap istio -n istio-system
# Add: accessLogFile: /dev/stdout
```

---

## Expected Bot Output

```
🚀 Initializing Slack bot...
🌐 Multi-cluster routing mode enabled
🔧 Kagent client initialized (multi-cluster routing mode)
   Clusters: test, dev, prod
   Default: test
   Using pattern-based routing: k8s-agent-{cluster}
   test: https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-test/
   dev: https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-dev/
   prod: https://kagent.yourdomain.com/api/a2a/kagent/k8s-agent-prod/
✅ Slack app initialized
⚡ Bot is running! Waiting for @mentions...
```

---

## Production Deployment

Once working, deploy bot as systemd service:

```bash
sudo systemctl enable kagent-slack-bot
sudo systemctl start kagent-slack-bot
sudo journalctl -u kagent-slack-bot -f
```

The bot can now run from **anywhere** (not just your local network) thanks to Cloudflare tunnel!
