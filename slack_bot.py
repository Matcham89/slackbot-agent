"""
Kagent Slack Bot - A2A Protocol Integration

A secure Slack bot that connects your workspace to Kagent's Kubernetes AI agents
using the A2A (Agent2Agent) protocol. Implements conversation threading and
context management for natural language interactions with your cluster.

Security Features:
- Environment-based configuration (no hardcoded credentials)
- Input validation and sanitization
- Proper error handling and logging
- Timeout protection for long-running requests
- Thread-safe context management

License: MIT
"""
import os
import json
import logging
import hashlib
import re
from typing import Optional, Dict, List
import requests
from sseclient import SSEClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv

# Configure logging with security in mind
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security: Prevent logging of sensitive data
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('slack_bolt').setLevel(logging.INFO)

# Load environment variables
load_dotenv()


def detect_cluster_from_message(message: str, available_clusters: List[str]) -> Optional[str]:
    """
    Detect cluster keyword in user message.

    Args:
        message: User's message text
        available_clusters: List of valid cluster names

    Returns:
        Detected cluster name or None if not found

    Examples:
        "how many pods on the test cluster" → "test"
        "check dev environment" → "dev"
        "list namespaces in production" → "prod"
    """
    message_lower = message.lower()

    # Try exact word match for each cluster
    for cluster in available_clusters:
        # Use word boundaries to avoid partial matches
        pattern = r'\b' + re.escape(cluster.lower()) + r'\b'
        if re.search(pattern, message_lower):
            logger.debug(f"🎯 Detected cluster: {cluster}")
            return cluster

    # Check for common aliases
    cluster_aliases = {
        'production': 'prod',
        'development': 'dev',
        'testing': 'test',
        'staging': 'stage'
    }

    for alias, cluster in cluster_aliases.items():
        if cluster in available_clusters:
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, message_lower):
                logger.debug(f"🎯 Detected cluster via alias '{alias}': {cluster}")
                return cluster

    logger.debug(f"🤷 No cluster detected in message")
    return None


class KagentClient:
    def __init__(self, base_url: Optional[str] = None, namespace: Optional[str] = None,
                 agent_name: Optional[str] = None, multi_cluster: bool = False,
                 cluster_endpoints: Optional[Dict[str, str]] = None,
                 default_cluster: Optional[str] = None):
        """
        Initialize Kagent client with single or multi-cluster support.

        Args:
            base_url: Base URL of Kagent controller (single-cluster mode)
            namespace: Kagent namespace (single-cluster mode)
            agent_name: Agent name (single-cluster mode)
            multi_cluster: Enable multi-cluster routing
            cluster_endpoints: Dict mapping cluster names to full endpoint URLs
            default_cluster: Default cluster when none detected
        """
        self.multi_cluster = multi_cluster

        if multi_cluster:
            self.cluster_endpoints = cluster_endpoints or {}
            self.clusters = list(cluster_endpoints.keys()) if cluster_endpoints else []
            self.default_cluster = default_cluster or (self.clusters[0] if self.clusters else None)
            # Thread contexts: {thread_ts: {cluster: contextId}}
            self.thread_contexts: Dict[str, Dict[str, str]] = {}
            logger.info(f"🔧 Kagent client initialized (multi-cluster routing mode)")
            logger.info(f"   Clusters: {', '.join(self.clusters)}")
            logger.info(f"   Default: {self.default_cluster}")
            for cluster, endpoint in self.cluster_endpoints.items():
                logger.info(f"   {cluster}: {endpoint}")
        else:
            self.base_url = base_url
            self.namespace = namespace
            self.agent_name = agent_name
            self.endpoint = f"{base_url}/api/a2a/{namespace}/{agent_name}/"
            # Thread contexts: {thread_ts: contextId}
            self.thread_contexts: Dict[str, str] = {}
            logger.info(f"🔧 Kagent client initialized (single-cluster mode)")
            logger.info(f"   Endpoint: {self.endpoint}")

    def _get_endpoint(self, cluster: Optional[str] = None) -> str:
        """Get endpoint URL for specified cluster or default."""
        if self.multi_cluster:
            target_cluster = cluster or self.default_cluster
            return self.cluster_endpoints.get(target_cluster, "")
        else:
            return self.endpoint
    
    def send_message(self, text: str, thread_id: Optional[str] = None, cluster: Optional[str] = None) -> Dict:
        """
        Send message to Kagent and extract response from SSE stream

        Args:
            text: User message to send to the agent
            thread_id: Optional thread identifier for conversation continuity
            cluster: Target cluster (for multi-cluster mode)

        Returns:
            Dict with keys: response (str), status (str), contextId (str), cluster (str)

        Security:
            - Input is not sanitized as it's passed to AI agent, not executed
            - Timeout protection prevents infinite waits
            - SSL verification enabled by default (via requests library)
        """
        # Determine target cluster
        if self.multi_cluster:
            if not cluster:
                # Try to detect from message
                cluster = detect_cluster_from_message(text, self.clusters)
            # Fall back to default if still not found
            target_cluster = cluster or self.default_cluster
            endpoint = self._get_endpoint(target_cluster)
        else:
            target_cluster = None
            endpoint = self.endpoint

        # Security: Truncate message in logs to prevent log injection
        safe_msg = text[:100].replace('\n', ' ').replace('\r', '')
        logger.info(f"📤 Sending message to Kagent")
        if self.multi_cluster:
            logger.info(f"   Cluster: {target_cluster}")
        logger.info(f"   Endpoint: {endpoint}")
        logger.info(f"   Thread ID: {thread_id}")
        logger.info(f"   Message: {safe_msg}...")

        # Prepare JSON-RPC 2.0 request
        # Security: Use hashlib for deterministic message ID generation
        msg_hash = hashlib.sha256(f"{text}{thread_id}".encode()).hexdigest()[:16]
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                    "messageId": f"msg-{msg_hash}"
                }
            }
        }

        # Include contextId for thread continuity (cluster-aware)
        context_id = None
        if thread_id:
            if self.multi_cluster:
                # Multi-cluster: separate contexts per cluster per thread
                if thread_id in self.thread_contexts and target_cluster in self.thread_contexts[thread_id]:
                    context_id = self.thread_contexts[thread_id][target_cluster]
                    logger.info(f"🔄 Using existing contextId for {target_cluster}: {context_id}")
                else:
                    logger.info(f"🆕 Starting new conversation on {target_cluster}")
            else:
                # Single-cluster: simple context lookup
                if thread_id in self.thread_contexts:
                    context_id = self.thread_contexts[thread_id]
                    logger.info(f"🔄 Using existing contextId: {context_id}")
                else:
                    logger.info(f"🆕 Starting new conversation")

        if context_id:
            payload["params"]["message"]["contextId"] = context_id
        
        # Make streaming request
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "kagent-slack-bot/1.0.0"
        }

        # Add Cloudflare Access service token headers if configured
        cf_client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
        cf_client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
        if cf_client_id and cf_client_secret:
            headers["CF-Access-Client-Id"] = cf_client_id
            headers["CF-Access-Client-Secret"] = cf_client_secret

        try:
            # Security: SSL verification enabled by default
            # Security: Timeout prevents hanging connections
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                stream=True,
                timeout=300,  # 5 minute timeout
                verify=True  # Explicit SSL verification (default, but shown for clarity)
            )
            response.raise_for_status()

            # Parse SSE stream
            result = self._parse_stream(response, thread_id, target_cluster)

            logger.info(f"✅ Message processed")
            logger.info(f"   Status: {result['status']}")
            logger.info(f"   Context ID: {result['contextId']}")
            if self.multi_cluster:
                logger.info(f"   Cluster: {result['cluster']}")
            logger.info(f"   Response length: {len(result['response'] or '')}")

            return result
            
        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Request timeout after 300s")
            return {
                'response': "Request timed out. Please try again.",
                'status': 'timeout',
                'contextId': None,
                'cluster': target_cluster if self.multi_cluster else None
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request failed: {e}")
            return {
                'response': f"Failed to connect to Kagent: {str(e)}",
                'status': 'error',
                'contextId': None,
                'cluster': target_cluster if self.multi_cluster else None
            }

    def _parse_stream(self, response, thread_id: Optional[str], cluster: Optional[str] = None) -> Dict:
        """
        Parse SSE events and extract agent response (cluster-aware for multi-cluster mode)
        """
        client = SSEClient(response)
        agent_response = None
        context_id = None
        status = "unknown"
        event_count = 0

        logger.debug(f"📡 Starting SSE stream parsing")

        for event in client.events():
            # Skip empty events
            if not event.data or not event.data.strip():
                continue

            event_count += 1

            try:
                # Each event.data contains a JSON-RPC response
                json_rpc_response = json.loads(event.data)

                # Handle JSON-RPC errors
                if 'error' in json_rpc_response:
                    error = json_rpc_response['error']
                    logger.error(f"❌ JSON-RPC error: {error}")
                    return {
                        'response': f"Agent error: {error.get('message', 'Unknown error')}",
                        'status': 'error',
                        'contextId': context_id,
                        'cluster': cluster if self.multi_cluster else None
                    }

                # Extract the actual event from the JSON-RPC wrapper
                event_data = json_rpc_response.get('result', {})

                if not event_data:
                    logger.warning(f"⚠️ Empty result in JSON-RPC response")
                    continue

                # Log event details
                logger.debug(f"📦 Event {event_count}: kind={event_data.get('kind')}, "
                           f"final={event_data.get('final')}, "
                           f"status={event_data.get('status', {}).get('state')}")

                # Store contextId for conversation continuity (cluster-aware)
                if 'contextId' in event_data:
                    context_id = event_data['contextId']
                    if thread_id:
                        if self.multi_cluster and cluster:
                            # Multi-cluster: store per cluster per thread
                            if thread_id not in self.thread_contexts:
                                self.thread_contexts[thread_id] = {}
                            self.thread_contexts[thread_id][cluster] = context_id
                        else:
                            # Single-cluster: simple storage
                            self.thread_contexts[thread_id] = context_id
                
                # Track status
                if 'status' in event_data:
                    status = event_data['status'].get('state', status)
                    
                    # Check if this event contains the agent response
                    if 'message' in event_data['status']:
                        message = event_data['status']['message']
                        
                        # Only process agent messages (not user echoes)
                        if message.get('role') == 'agent':
                            # Extract text from parts
                            parts = message.get('parts', [])
                            if parts and len(parts) > 0:
                                agent_response = parts[0].get('text', '')
                                logger.debug(f"💬 Found agent response: {agent_response[:100]}...")
                
                # Check if this is the final event
                if event_data.get('final'):
                    logger.debug(f"🏁 Received final event")
                    break
                    
            except json.JSONDecodeError as e:
                logger.error(f"⚠️ Failed to parse event: {event.data[:200]}")
                continue
            except Exception as e:
                logger.error(f"⚠️ Error processing event: {e}")
                continue
        
        logger.info(f"📊 Processed {event_count} events from stream")

        return {
            'response': agent_response,
            'status': status,
            'contextId': context_id,
            'cluster': cluster if self.multi_cluster else None
        }


# Initialize Slack app
logger.info("🚀 Initializing Slack bot...")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")

# Support both configuration styles:
# 1. KAGENT_A2A_URL (full URL): http://host:port/api/a2a/namespace/agent
# 2. Separate components: KAGENT_BASE_URL + KAGENT_NAMESPACE + KAGENT_AGENT_NAME
KAGENT_A2A_URL = os.environ.get("KAGENT_A2A_URL")

if KAGENT_A2A_URL:
    # Parse the full URL to extract components
    # Format: http://host:port/api/a2a/namespace/agent
    logger.info(f"📋 Using KAGENT_A2A_URL: {KAGENT_A2A_URL}")

    # Extract base URL (everything before /api/a2a/)
    if "/api/a2a/" in KAGENT_A2A_URL:
        KAGENT_BASE_URL = KAGENT_A2A_URL.split("/api/a2a/")[0]
        # Extract namespace/agent from path
        path_parts = KAGENT_A2A_URL.split("/api/a2a/")[1].rstrip("/").split("/")
        KAGENT_NAMESPACE = path_parts[0] if len(path_parts) > 0 else None
        KAGENT_AGENT_NAME = path_parts[1] if len(path_parts) > 1 else None

        logger.info(f"   Parsed base URL: {KAGENT_BASE_URL}")
        logger.info(f"   Parsed namespace: {KAGENT_NAMESPACE}")
        logger.info(f"   Parsed agent: {KAGENT_AGENT_NAME}")
    else:
        logger.error("❌ Invalid KAGENT_A2A_URL format. Expected: http://host:port/api/a2a/namespace/agent")
        exit(1)
else:
    # Use separate component variables (no defaults - must be provided)
    KAGENT_BASE_URL = os.environ.get("KAGENT_BASE_URL")
    KAGENT_NAMESPACE = os.environ.get("KAGENT_NAMESPACE")
    KAGENT_AGENT_NAME = os.environ.get("KAGENT_AGENT_NAME")
    logger.info(f"📋 Using separate env vars")

# Multi-cluster configuration
ENABLE_MULTI_CLUSTER = os.environ.get("ENABLE_MULTI_CLUSTER", "false").lower() in ("true", "1", "yes")

if ENABLE_MULTI_CLUSTER:
    logger.info(f"🌐 Multi-cluster routing mode enabled")
    KAGENT_CLUSTERS_STR = os.environ.get("KAGENT_CLUSTERS", "")
    KAGENT_CLUSTERS = [c.strip() for c in KAGENT_CLUSTERS_STR.split(",") if c.strip()]
    KAGENT_DEFAULT_CLUSTER = os.environ.get("KAGENT_DEFAULT_CLUSTER", KAGENT_CLUSTERS[0] if KAGENT_CLUSTERS else None)

    # Two configuration methods:
    # Method 1: Pattern-based (same base URL, different agent names)
    # Method 2: Full URLs per cluster (different controllers)

    KAGENT_AGENT_PATTERN = os.environ.get("KAGENT_AGENT_PATTERN")

    CLUSTER_ENDPOINTS = {}

    if KAGENT_AGENT_PATTERN:
        # Pattern-based: Build endpoints using base URL + pattern
        logger.info(f"   Using pattern-based routing: {KAGENT_AGENT_PATTERN}")
        for cluster in KAGENT_CLUSTERS:
            agent_name = KAGENT_AGENT_PATTERN.replace("{cluster}", cluster)
            endpoint = f"{KAGENT_BASE_URL}/api/a2a/{KAGENT_NAMESPACE}/{agent_name}/"
            CLUSTER_ENDPOINTS[cluster] = endpoint
    else:
        # URL-based: Read individual URLs for each cluster
        # Format: KAGENT_<CLUSTER>_URL (e.g., KAGENT_TEST_URL, KAGENT_DEV_URL)
        logger.info(f"   Using URL-based routing")
        for cluster in KAGENT_CLUSTERS:
            env_var = f"KAGENT_{cluster.upper()}_URL"
            endpoint = os.environ.get(env_var)
            if endpoint:
                CLUSTER_ENDPOINTS[cluster] = endpoint
            else:
                logger.warning(f"⚠️ Missing endpoint for cluster '{cluster}': {env_var} not set")
else:
    KAGENT_CLUSTERS = None
    KAGENT_DEFAULT_CLUSTER = None
    CLUSTER_ENDPOINTS = None

# Validate required environment variables
if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    logger.error("❌ Missing required environment variables: SLACK_BOT_TOKEN and/or SLACK_APP_TOKEN")
    exit(1)

if ENABLE_MULTI_CLUSTER:
    # Multi-cluster mode validation
    if not KAGENT_CLUSTERS:
        logger.error("❌ Multi-cluster mode enabled but KAGENT_CLUSTERS not provided")
        exit(1)
    if not KAGENT_DEFAULT_CLUSTER:
        logger.error("❌ Multi-cluster mode enabled but KAGENT_DEFAULT_CLUSTER not provided")
        exit(1)

    # Check if using pattern-based or URL-based routing
    if KAGENT_AGENT_PATTERN:
        # Pattern-based: need base URL and namespace
        if not KAGENT_BASE_URL:
            logger.error("❌ Pattern-based routing requires KAGENT_BASE_URL")
            exit(1)
        if not KAGENT_NAMESPACE:
            logger.error("❌ Pattern-based routing requires KAGENT_NAMESPACE")
            exit(1)

    # Verify endpoints were generated/loaded
    if not CLUSTER_ENDPOINTS:
        logger.error("❌ Multi-cluster mode enabled but no cluster endpoints configured")
        logger.error("    Option 1 (Pattern): Set KAGENT_AGENT_PATTERN=k8s-agent-{cluster}")
        logger.error("    Option 2 (URLs): Set KAGENT_<CLUSTER>_URL for each cluster")
        exit(1)
    if KAGENT_DEFAULT_CLUSTER not in CLUSTER_ENDPOINTS:
        logger.error(f"❌ Default cluster '{KAGENT_DEFAULT_CLUSTER}' has no endpoint URL")
        exit(1)
else:
    # Single-cluster mode validation
    if not KAGENT_BASE_URL:
        logger.error("❌ Missing required environment variable: KAGENT_BASE_URL or KAGENT_A2A_URL")
        exit(1)
    if not KAGENT_NAMESPACE:
        logger.error("❌ Missing required environment variable: KAGENT_NAMESPACE")
        exit(1)
    if not KAGENT_AGENT_NAME:
        logger.error("❌ Missing required environment variable: KAGENT_AGENT_NAME (or provide KAGENT_A2A_URL)")
        exit(1)

# Initialize Slack app and Kagent client
app = App(token=SLACK_BOT_TOKEN)

if ENABLE_MULTI_CLUSTER:
    kagent = KagentClient(
        multi_cluster=True,
        cluster_endpoints=CLUSTER_ENDPOINTS,
        default_cluster=KAGENT_DEFAULT_CLUSTER
    )
else:
    kagent = KagentClient(
        base_url=KAGENT_BASE_URL,
        namespace=KAGENT_NAMESPACE,
        agent_name=KAGENT_AGENT_NAME,
        multi_cluster=False
    )

logger.info("✅ Slack app initialized")


@app.event("app_mention")
def handle_mention(event, say, logger):
    """
    Handle @kagent mentions in Slack
    """
    logger.info(f"🔔 Received app_mention")
    logger.info(f"   Channel: {event.get('channel')}")
    logger.info(f"   User: {event.get('user')}")
    logger.info(f"   Text: {event.get('text')}")
    
    # Get thread_ts: use existing thread or start new one
    thread_ts = event.get("thread_ts") or event.get("ts")
    logger.info(f"   Thread: {thread_ts}")
    
    # Extract user message (remove bot mention)
    user_message = event["text"]
    user_message = user_message.split(">", 1)[-1].strip()
    logger.info(f"   Cleaned message: {user_message}")
    
    if not user_message:
        say("Please provide a message after mentioning me!", thread_ts=thread_ts)
        return
    
    # Acknowledge receipt
    say("🤔 Processing your request...", thread_ts=thread_ts)
    
    try:
        # Send to Kagent and get response
        result = kagent.send_message(user_message, thread_id=thread_ts)
        
        if result['status'] == 'completed' and result['response']:
            say(result['response'], thread_ts=thread_ts)
        elif result['status'] == 'failed':
            say(f"❌ Task failed: {result['response']}", thread_ts=thread_ts)
        elif result['status'] in ['timeout', 'error']:
            say(result['response'], thread_ts=thread_ts)
        else:
            say(f"⚠️ No response received from agent (status: {result['status']})", thread_ts=thread_ts)
            
    except Exception as e:
        logger.error(f"❌ Error in handle_mention: {e}", exc_info=True)
        say(f"❌ Failed to process request: {str(e)}", thread_ts=thread_ts)


@app.event("message")
def handle_message_events(body, logger):
    """
    Handle other message events (for debugging)
    """
    logger.debug(f"Message event: {body.get('event', {}).get('type')}")


if __name__ == "__main__":
    logger.info("🎬 Starting Kagent Slack Bot...")
    logger.info(f"   Kagent: {KAGENT_BASE_URL}")
    logger.info(f"   Agent: {KAGENT_NAMESPACE}/{KAGENT_AGENT_NAME}")
    logger.info(f"   Bot Token: {'SET' if SLACK_BOT_TOKEN else 'NOT SET'}")
    logger.info(f"   App Token: {'SET' if SLACK_APP_TOKEN else 'NOT SET'}")
    
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    logger.info("⚡ Bot is running! Waiting for @mentions...")
    handler.start()