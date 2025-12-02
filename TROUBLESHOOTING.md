# Troubleshooting: "No address associated with hostname"

## Error Description

```
Error: no address associated with hostname
```

This means your Debian server cannot resolve the hostname in `KAGENT_BASE_URL`.

---

## Step 1: Check Your Configuration

```bash
# On your Debian server, check what hostname you're using
grep KAGENT_BASE_URL .env
```

**Common incorrect values:**
- `kagent-controller` (only works inside Kubernetes)
- `kagent-controller.kagent.svc.cluster.local` (Kubernetes internal DNS)
- Any hostname without proper DNS setup

---

## Step 2: Test DNS Resolution

```bash
# Try to resolve the hostname
nslookup kagent-controller
# or
dig kagent-controller

# If this fails, the hostname is not resolvable
```

---

## Solutions

### Solution 1: Use Port-Forward (Recommended for Testing)

**On your Debian server:**

```bash
# Connect to your Kubernetes cluster
kubectl config use-context your-cluster-context

# Port-forward the Kagent controller
kubectl port-forward -n kagent svc/kagent-controller 8083:8083

# This runs in foreground, open a new terminal for the bot
```

**Update `.env` to use localhost:**
```bash
KAGENT_BASE_URL=http://localhost:8083
```

**Run the bot:**
```bash
source venv/bin/activate
python slack_bot.py
```

---

### Solution 2: Use Direct IP Address

**Find the external IP/LoadBalancer of Kagent controller:**

```bash
# Get service details
kubectl get svc -n kagent kagent-controller

# If it has an EXTERNAL-IP, use that
# Example output:
# NAME                 TYPE           EXTERNAL-IP      PORT(S)
# kagent-controller    LoadBalancer   34.123.45.67     8083:30123/TCP
```

**Update `.env` with IP address:**
```bash
KAGENT_BASE_URL=http://34.123.45.67:8083
```

---

### Solution 3: Add Hostname to /etc/hosts

**If you know the IP of your Kagent controller:**

```bash
# Find the IP
kubectl get nodes -o wide  # Get node IP where Kagent runs
# or
kubectl get svc -n kagent kagent-controller  # Get service IP

# Add to /etc/hosts
sudo nano /etc/hosts

# Add this line (replace with actual IP):
10.0.1.50    kagent-controller
```

**Update `.env`:**
```bash
KAGENT_BASE_URL=http://kagent-controller:8083
```

---

### Solution 4: Use NodePort

**Expose Kagent controller via NodePort:**

```bash
# Check if already using NodePort
kubectl get svc -n kagent kagent-controller

# If not, patch the service
kubectl patch svc kagent-controller -n kagent -p '{"spec":{"type":"NodePort"}}'

# Get the NodePort
kubectl get svc -n kagent kagent-controller
# Example output:
# NAME                 TYPE       PORT(S)
# kagent-controller    NodePort   8083:30123/TCP
#                                      ^^^^^ This is the NodePort
```

**Update `.env` with Node IP + NodePort:**
```bash
# Get node IP
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="ExternalIP")].address}')

# Use in .env
KAGENT_BASE_URL=http://${NODE_IP}:30123
```

---

### Solution 5: VPN/Tailscale (Production Setup)

**If you have VPN access to the cluster network:**

1. Connect to VPN/Tailscale network
2. Use the internal cluster IP

```bash
# Get internal service IP
kubectl get svc -n kagent kagent-controller -o jsonpath='{.spec.clusterIP}'

# Update .env with cluster IP
KAGENT_BASE_URL=http://10.96.123.45:8083
```

---

## Recommended Setup per Environment

### Local Laptop
```bash
# Use port-forward
kubectl port-forward -n kagent svc/kagent-controller 8083:8083
KAGENT_BASE_URL=http://localhost:8083
```

### Debian Server (Same Network as Cluster)
```bash
# Use NodePort or LoadBalancer IP
KAGENT_BASE_URL=http://node-ip:30123
# or
KAGENT_BASE_URL=http://loadbalancer-ip:8083
```

### Debian Server (Remote)
```bash
# Use VPN + internal IP or set up ingress
KAGENT_BASE_URL=http://cluster-internal-ip:8083
```

---

## Testing the Fix

After updating `KAGENT_BASE_URL`, test connectivity:

```bash
# Test the endpoint
curl http://your-kagent-url:8083/api/a2a/kagent/k8s-agent-test/.well-known/agent.json

# Should return JSON, not error
```

**If curl works, restart the bot:**
```bash
# If running as service
sudo systemctl restart kagent-slack-bot

# If running manually
# Ctrl+C to stop, then
python slack_bot.py
```

---

## Quick Fix Commands

```bash
# 1. Check current configuration
grep KAGENT_BASE_URL .env

# 2. Test if hostname resolves
ping $(grep KAGENT_BASE_URL .env | cut -d'/' -f3 | cut -d':' -f1)

# 3. If not, use port-forward
kubectl port-forward -n kagent svc/kagent-controller 8083:8083 &

# 4. Update .env
sed -i 's|KAGENT_BASE_URL=.*|KAGENT_BASE_URL=http://localhost:8083|' .env

# 5. Restart bot
python slack_bot.py
```

---

## Still Having Issues?

Check logs for more details:

```bash
# If running as service
sudo journalctl -u kagent-slack-bot -n 50

# Look for the exact error line showing which hostname failed
```

Common issues:
- ❌ Using `kagent-controller` outside Kubernetes
- ❌ Using `.svc.cluster.local` outside Kubernetes
- ❌ Firewall blocking connection
- ❌ Kagent controller not running
- ❌ Wrong port number

Share the output of:
```bash
echo "Config: $(grep KAGENT_BASE_URL .env)"
kubectl get svc -n kagent kagent-controller
```
