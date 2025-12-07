-----

# Kagent Slack Bot - AI Orchestrator Edition

A "Senior Engineer" Slack bot that orchestrates Kubernetes tasks across multiple clusters using a Local LLM Brain.

Unlike simple chatbots, this bot uses a **Map-Reduce Architecture**:

1.  **Plan:** The AI Brain analyzes complex requests (e.g., "Compare dev and test").
2.  **Map:** It dispatches targeted queries to specific agents on different clusters.
3.  **Reduce:** It synthesizes the data returned from all clusters into a single, comparative report.

## Architecture

```mermaid
graph TD
    User((User)) -->|Slack| Bot[Python Slack Bot]
    
    subgraph "The Brain (Remote/Local)"
        Bot <-->|JSON Plans| Ollama[Ollama Server]
        note[Running Llama 3.2 or Qwen 2.5]
    end
    
    subgraph "Infrastructure"
        Bot -->|a2a Protocol| AgentTest[AgentGateway: Test]
        Bot -->|a2a Protocol| AgentDev[AgentGateway: Dev]
    end
    
    AgentTest --> K8sTest((Test Cluster))
    AgentDev --> K8sDev((Dev Cluster))
```

## Prerequisites

  - **Python 3.13+**
  - **Ollama Server** running and accessible.
      - Recommended Models: `llama3.2` (3B) for speed, or `qwen2.5:32b` for complex reasoning.
  - **AgentGateway** deployed on your target clusters (Port 8080).
  - **Network Access**:
      - The bot must reach the AgentGateway IPs.
      - The bot must reach the Ollama API (Port 11434 or via Istio Gateway).

-----

## Installation

### 1\. Clone and Setup

```bash
git clone https://github.com/your-org/kagent-slack-bot.git
cd kagent-slack-bot

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies (ensure 'ollama' lib is included)
pip install -r requirements.txt
```

### 2\. Configuration (.env)

Create a `.env` file based on the example.

```bash
cp .env.example .env
nano .env
```

**Required Configuration:**

```bash
# --- Slack Credentials ---
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_APP_TOKEN=xapp-your-token

# --- AI Brain Configuration ---
# Option A: Running locally on the same machine
# OLLAMA_HOST=http://localhost:11434

# Option B: Running on K8s via Istio Gateway (Recommended)
OLLAMA_HOST=http://ollama.dev.local

# Option C: Running on Dedicated AI Server IP
# OLLAMA_HOST=http://192.168.1.55:11434

# --- Multi-Cluster Setup ---
ENABLE_MULTI_CLUSTER=true
KAGENT_CLUSTERS=test,dev
KAGENT_DEFAULT_CLUSTER=test

# --- Cluster Endpoints (AgentGateway) ---
KAGENT_TEST_BASE_URL=http://192.168.1.200:8080
KAGENT_DEV_BASE_URL=http://192.168.1.201:8080

# --- Agent Config ---
KAGENT_NAMESPACE=kagent
KAGENT_AGENT_PATTERN=k8s-agent
```

### 3\. DNS & Network (Crucial for Remote Brain)

If you are hosting Ollama on your Kubernetes cluster behind an **Istio Gateway** (e.g., `ollama.dev.local`), you must map the domain to the Gateway IP.

1.  **Get Gateway IP:**

    ```bash
    kubectl get svc -n istio-system istio-gateway
    # Example EXTERNAL-IP: 192.168.1.202
    ```

2.  **Update Hosts File (On the machine running the bot):**

    ```bash
    sudo nano /etc/hosts
    ```

    Add the line:

    ```text
    192.168.1.202  ollama.dev.local
    ```

### 4\. Run the Bot

```bash
source venv/bin/activate
python slack_bot.py
```

**Expected Output:**

```text
🧠 Connecting to Brain at: http://ollama.dev.local
🔧 Kagent client initialized (multi-cluster)
✅ System initialized (Mode: TARGETED MAP-REDUCE)
🎬 Starting Bot...
⚡️ Bolt app is running!
```

-----

## Usage Examples

Once running, the bot acts as an intelligent orchestrator.

### 1\. Multi-Cluster Comparison (Map-Reduce)

*Ask the bot to compare resources across environments. The AI will split this into two tasks, fetch the data, and synthesize a report.*

> **User:** `@kagent compare the deployments in test and dev`
>
> **Bot:**
> 🔄 Fetching from **test**...
> 🔄 Fetching from **dev**...
> 🧠 Analyzing...
> **Comparison Report:**
>
>   - Deployment `kagent-controller` exists in both.
>   - **Difference:** Test is running v0.7.1, Dev is running v0.7.5.

### 2\. Targeted Resource Lookup

*Ask about a specific resource to prevent data flooding.*

> **User:** `@kagent what is the status of the redis pod in dev?`
>
> **Bot:** (Fetches ONLY the redis pod details from Dev)

### 3\. General Inquiry

> **User:** `@kagent how many namespaces are in test?`

-----

## Troubleshooting

### `Brain Plan Error: Failed to connect to Ollama`

  * **Cause:** The bot cannot reach the `OLLAMA_HOST`.
  * **Fix:**
      * Verify the URL in `.env`.
      * If using Istio, verify `/etc/hosts` is set.
      * Test via curl: `curl http://ollama.dev.local/api/tags`

### `404 Not Found` (Istio/Gateway)

  * **Cause:** The Gateway is rejecting the hostname.
  * **Fix:** Ensure your `HTTPRoute` references the correct parent Gateway and that the Gateway allows routes from the target namespace (`from: All`).

### `Timeout` / Slow Responses

  * **Cause:** Using a large model (32B/70B) on a CPU.
  * **Fix:** Increase the timeout in `slack_bot.py`:
    ```python
    response = requests.post(..., timeout=120)
    ```

### Bot Hallucinations (e.g., "The user prompt")

  * **Cause:** Using a small model (1B) that overfits to system prompt examples.
  * **Fix:** Upgrade to `llama3.2` (3B) or `qwen2.5:32b`. The current codebase uses "Zero-Shot" prompting to minimize this.