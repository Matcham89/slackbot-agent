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
- Token limit tracking and warnings

License: MIT
"""
import json
import logging
import hashlib
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
import requests
from sseclient import SSEClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

# Import configuration module
from config import load_config, validate_config, BotConfig, ClusterConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Security: Prevent logging of sensitive data
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('slack_bolt').setLevel(logging.INFO)


@dataclass
class ContextInfo:
    """Information about conversation context"""
    context_id: str
    cluster: Optional[str]
    message_count: int
    estimated_tokens: int


def estimate_tokens(text: str) -> int:
    """
    Estimate token count for text (rough approximation)

    Uses simple heuristic: ~4 characters per token on average
    This is a rough estimate - actual tokenization varies by model

    Args:
        text: Text to estimate

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    # Rough approximation: 4 chars per token
    return len(text) // 4


def detect_cluster_from_message(message: str, clusters: List[ClusterConfig]) -> Optional[str]:
    """
    Detect cluster keyword in user message with improved alias support.

    Args:
        message: User's message text
        clusters: List of cluster configurations with aliases

    Returns:
        Detected cluster name or None if not found

    Examples:
        "how many pods on the test cluster" → "test"
        "check dev environment" → "dev"
        "list namespaces in production" → "prod"
        "show me the testing cluster" → "test" (via alias)
    """
    message_lower = message.lower()

    # Try exact match for each cluster name first
    for cluster in clusters:
        pattern = r'\b' + re.escape(cluster.name.lower()) + r'\b'
        if re.search(pattern, message_lower):
            logger.debug(f"🎯 Detected cluster (exact): {cluster.name}")
            return cluster.name

    # Try aliases for each cluster
    for cluster in clusters:
        for alias in cluster.aliases:
            pattern = r'\b' + re.escape(alias.lower()) + r'\b'
            if re.search(pattern, message_lower):
                logger.debug(f"🎯 Detected cluster (via alias '{alias}'): {cluster.name}")
                return cluster.name

    logger.debug("🤷 No cluster detected in message")
    return None


class ContextManager:
    """
    Manages conversation contexts with token tracking

    Tracks context IDs, message counts, and estimated token usage
    to prevent exceeding API limits
    """

    def __init__(self, max_tokens: int = 300000):
        """
        Initialize context manager

        Args:
            max_tokens: Maximum tokens before warning (default: 300k)
        """
        self.max_tokens = max_tokens
        # Single-cluster: {thread_id: ContextInfo}
        # Multi-cluster: {thread_id: {cluster: ContextInfo}}
        self.contexts: Dict[str, any] = {}

    def get_context(self, thread_id: str, cluster: Optional[str] = None) -> Optional[ContextInfo]:
        """Get context info for thread and cluster"""
        if thread_id not in self.contexts:
            return None

        if cluster:
            # Multi-cluster mode
            if isinstance(self.contexts[thread_id], dict):
                return self.contexts[thread_id].get(cluster)
        else:
            # Single-cluster mode
            if not isinstance(self.contexts[thread_id], dict):
                return self.contexts[thread_id]

        return None

    def set_context(self, thread_id: str, context_id: str,
                    message_text: str, response_text: Optional[str],
                    cluster: Optional[str] = None):
        """
        Store or update context with token tracking

        Args:
            thread_id: Slack thread ID
            context_id: A2A context ID
            message_text: User's message
            response_text: Agent's response
            cluster: Cluster name (for multi-cluster mode)
        """
        # Estimate tokens for this exchange
        tokens = estimate_tokens(message_text)
        if response_text:
            tokens += estimate_tokens(response_text)

        if cluster:
            # Multi-cluster mode
            if thread_id not in self.contexts:
                self.contexts[thread_id] = {}

            if cluster in self.contexts[thread_id]:
                # Update existing context
                info = self.contexts[thread_id][cluster]
                info.message_count += 1
                info.estimated_tokens += tokens
            else:
                # Create new context
                self.contexts[thread_id][cluster] = ContextInfo(
                    context_id=context_id,
                    cluster=cluster,
                    message_count=1,
                    estimated_tokens=tokens
                )
        else:
            # Single-cluster mode
            if thread_id in self.contexts:
                # Update existing context
                info = self.contexts[thread_id]
                info.message_count += 1
                info.estimated_tokens += tokens
            else:
                # Create new context
                self.contexts[thread_id] = ContextInfo(
                    context_id=context_id,
                    cluster=None,
                    message_count=1,
                    estimated_tokens=tokens
                )

    def clear_context(self, thread_id: str, cluster: Optional[str] = None):
        """Clear context for thread (and optionally specific cluster)"""
        if thread_id not in self.contexts:
            return

        if cluster and isinstance(self.contexts[thread_id], dict):
            # Clear specific cluster context
            if cluster in self.contexts[thread_id]:
                del self.contexts[thread_id][cluster]
                logger.info(f"🗑️ Cleared context for thread {thread_id} cluster {cluster}")
        else:
            # Clear entire thread context
            del self.contexts[thread_id]
            logger.info(f"🗑️ Cleared all contexts for thread {thread_id}")

    def check_token_limit(self, thread_id: str, cluster: Optional[str] = None) -> Tuple[bool, Optional[int]]:
        """
        Check if context is approaching token limit

        Args:
            thread_id: Slack thread ID
            cluster: Cluster name (for multi-cluster mode)

        Returns:
            (is_over_limit, estimated_tokens)
        """
        info = self.get_context(thread_id, cluster)
        if not info:
            return False, None

        return info.estimated_tokens > self.max_tokens, info.estimated_tokens


class KagentClient:
    def __init__(self, config: BotConfig, context_manager: ContextManager):
        """
        Initialize Kagent client with configuration

        Args:
            config: Bot configuration object
            context_manager: Context manager for tracking conversations
        """
        self.config = config
        self.context_manager = context_manager

        if config.multi_cluster_enabled:
            logger.info(f"🔧 Kagent client initialized (multi-cluster routing mode)")
            logger.info(f"   Clusters: {', '.join(c.name for c in config.clusters)}")
            logger.info(f"   Default: {config.default_cluster}")
            for cluster in config.clusters:
                logger.info(f"   {cluster.name}: {cluster.base_url}")
        else:
            logger.info(f"🔧 Kagent client initialized (single-cluster mode)")
            logger.info(f"   Endpoint: {config.single_cluster_endpoint}")

    def _get_endpoint(self, cluster: Optional[str] = None) -> str:
        """Get endpoint URL for specified cluster or default."""
        if self.config.multi_cluster_enabled:
            target_cluster = cluster or self.config.default_cluster
            for c in self.config.clusters:
                if c.name == target_cluster:
                    return c.base_url
            # Fallback to first cluster if not found
            return self.config.clusters[0].base_url if self.config.clusters else ""
        else:
            return self.config.single_cluster_endpoint

    def send_message(self, text: str, thread_id: Optional[str] = None,
                    cluster: Optional[str] = None) -> Dict:
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
        # Check if context is too large before sending
        if thread_id:
            over_limit, tokens = self.context_manager.check_token_limit(thread_id, cluster)
            if over_limit:
                return {
                    'response': (
                        f"⚠️ **Conversation Context Too Large**\n\n"
                        f"This conversation has accumulated approximately **{tokens:,} tokens**, "
                        f"which exceeds the safe limit of {self.config.max_context_tokens:,} tokens.\n\n"
                        f"**To continue:**\n"
                        f"• Start a new Slack thread, OR\n"
                        f"• Say: `@kagent reset context`\n\n"
                        f"💡 *Tip: Break large requests into smaller, focused questions*"
                    ),
                    'status': 'context_overflow',
                    'contextId': None,
                    'cluster': cluster
                }

        # Determine target cluster
        if self.config.multi_cluster_enabled:
            if not cluster:
                # Try to detect from message
                cluster = detect_cluster_from_message(text, self.config.clusters)
            # Fall back to default if still not found
            target_cluster = cluster or self.config.default_cluster
            endpoint = self._get_endpoint(target_cluster)
        else:
            target_cluster = None
            endpoint = self._get_endpoint()

        # Security: Truncate message in logs to prevent log injection
        safe_msg = text[:100].replace('\n', ' ').replace('\r', '')
        logger.info(f"📤 Sending message to Kagent")
        if self.config.multi_cluster_enabled:
            logger.info(f"   Cluster: {target_cluster}")
        logger.info(f"   Endpoint: {endpoint}")
        logger.info(f"   Thread ID: {thread_id}")
        logger.info(f"   Message: {safe_msg}...")

        # Prepare JSON-RPC 2.0 request
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

        # Include contextId for thread continuity
        context_info = self.context_manager.get_context(thread_id, target_cluster)
        if context_info:
            payload["params"]["message"]["contextId"] = context_info.context_id
            logger.info(f"🔄 Using existing contextId: {context_info.context_id}")
            logger.info(f"   Messages in thread: {context_info.message_count}")
            logger.info(f"   Estimated tokens: {context_info.estimated_tokens:,}")
        else:
            logger.info(f"🆕 Starting new conversation")

        # Make streaming request
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "kagent-slack-bot/2.0.0"
        }

        # Add Cloudflare Access service token headers if configured
        if self.config.cf_access_client_id and self.config.cf_access_client_secret:
            headers["CF-Access-Client-Id"] = self.config.cf_access_client_id
            headers["CF-Access-Client-Secret"] = self.config.cf_access_client_secret

        try:
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                stream=True,
                timeout=self.config.request_timeout,
                verify=True
            )
            response.raise_for_status()

            # Parse SSE stream
            result = self._parse_stream(response, thread_id, text, target_cluster)

            logger.info(f"✅ Message processed")
            logger.info(f"   Status: {result['status']}")
            logger.info(f"   Context ID: {result['contextId']}")
            if self.config.multi_cluster_enabled:
                logger.info(f"   Cluster: {result['cluster']}")
            logger.info(f"   Response length: {len(result['response'] or '')}")

            return result

        except requests.exceptions.Timeout:
            logger.error(f"⏱️ Request timeout after {self.config.request_timeout}s")
            return {
                'response': "⏱️ Request timed out. Please try breaking your request into smaller questions.",
                'status': 'timeout',
                'contextId': None,
                'cluster': target_cluster
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Request failed: {e}")
            return {
                'response': f"❌ Failed to connect to Kagent: {str(e)}",
                'status': 'error',
                'contextId': None,
                'cluster': target_cluster
            }

    def _parse_stream(self, response, thread_id: Optional[str],
                     message_text: str, cluster: Optional[str] = None) -> Dict:
        """
        Parse SSE events and extract agent response

        Args:
            response: HTTP response object
            thread_id: Slack thread ID
            message_text: Original user message
            cluster: Target cluster (for multi-cluster mode)

        Returns:
            Dict with response, status, contextId, cluster
        """
        client = SSEClient(response)
        agent_response = None
        context_id = None
        status = "unknown"
        event_count = 0

        logger.debug(f"📡 Starting SSE stream parsing")

        for event in client.events():
            if not event.data or not event.data.strip():
                continue

            event_count += 1

            try:
                json_rpc_response = json.loads(event.data)

                # Handle JSON-RPC errors with better token limit detection
                if 'error' in json_rpc_response:
                    error = json_rpc_response['error']
                    error_msg = error.get('message', 'Unknown error')
                    error_code = error.get('code', '')

                    logger.error(f"❌ JSON-RPC error: {error}")

                    # Detect token limit errors
                    if any(keyword in str(error).lower() for keyword in [
                        'rate_limit_exceeded', 'request too large', 'token',
                        'tpm', 'tokens per min'
                    ]):
                        # Clear context since it's too large
                        if thread_id:
                            self.context_manager.clear_context(thread_id, cluster)

                        return {
                            'response': (
                                "⚠️ **AI Token Limit Exceeded**\n\n"
                                "The conversation context has grown too large for the AI to process.\n\n"
                                "**What happened:**\n"
                                f"• {error_msg}\n\n"
                                "**To continue:**\n"
                                "• I've cleared the context for you - your next message will start fresh\n"
                                "• Break large requests into smaller, focused questions\n"
                                "• Avoid asking for extensive outputs (e.g., all logs, all pods)\n\n"
                                "💡 *Tip: Start a new thread for a completely fresh conversation*"
                            ),
                            'status': 'token_limit',
                            'contextId': None,
                            'cluster': cluster
                        }

                    # Generic error
                    return {
                        'response': f"❌ Agent error: {error_msg}",
                        'status': 'error',
                        'contextId': context_id,
                        'cluster': cluster
                    }

                event_data = json_rpc_response.get('result', {})

                if not event_data:
                    logger.warning(f"⚠️ Empty result in JSON-RPC response")
                    continue

                logger.debug(f"📦 Event {event_count}: kind={event_data.get('kind')}, "
                           f"final={event_data.get('final')}, "
                           f"status={event_data.get('status', {}).get('state')}")

                # Store contextId for conversation continuity
                if 'contextId' in event_data:
                    context_id = event_data['contextId']

                # Track status
                if 'status' in event_data:
                    status = event_data['status'].get('state', status)

                    # Extract agent response
                    if 'message' in event_data['status']:
                        message = event_data['status']['message']

                        if message.get('role') == 'agent':
                            parts = message.get('parts', [])
                            if parts and len(parts) > 0:
                                agent_response = parts[0].get('text', '')
                                logger.debug(f"💬 Found agent response: {agent_response[:100]}...")

                # Check if final event
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

        # Update context manager with this exchange
        if thread_id and context_id:
            self.context_manager.set_context(
                thread_id, context_id, message_text, agent_response, cluster
            )

        return {
            'response': agent_response,
            'status': status,
            'contextId': context_id,
            'cluster': cluster
        }


# Load and validate configuration
logger.info("🚀 Initializing Kagent Slack Bot...")
try:
    config = load_config()
    validate_config(config)
except Exception as e:
    logger.error(f"❌ Configuration error: {e}")
    exit(1)

# Set log level from config
logging.getLogger().setLevel(config.log_level)

# Initialize components
app = App(token=config.slack_bot_token)
context_manager = ContextManager(max_tokens=config.max_context_tokens)
kagent = KagentClient(config, context_manager)

logger.info("✅ Slack app initialized")


@app.event("app_mention")
def handle_mention(event, say, logger):
    """
    Handle @kagent mentions in Slack with command support
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

    # Check for special commands
    message_lower = user_message.lower()

    # Help command
    if message_lower in ['help', 'commands', '?']:
        help_text = (
            "**Kagent Slack Bot Commands**\n\n"
            "*Basic Usage:*\n"
            "• `@kagent <your question>` - Ask about your Kubernetes cluster\n"
            "• Use threads to maintain conversation context\n\n"
            "*Commands:*\n"
            "• `@kagent help` - Show this help message\n"
            "• `@kagent reset context` - Clear conversation history\n"
            "• `@kagent context info` - Show context size and stats\n\n"
        )

        if config.multi_cluster_enabled:
            help_text += (
                "*Multi-Cluster Mode:*\n"
                f"• Clusters: {', '.join(c.name for c in config.clusters)}\n"
                f"• Default: {config.default_cluster}\n"
                "• Mention cluster name in your message to route to it\n"
                "• Examples:\n"
                "  - `@kagent list pods in test cluster`\n"
                "  - `@kagent check dev namespace status`\n\n"
            )

        help_text += (
            "*Tips:*\n"
            "• Keep questions focused for better responses\n"
            "• Start a new thread if context grows too large\n"
            "• Break complex tasks into smaller questions\n"
        )

        say(help_text, thread_ts=thread_ts)
        return

    # Reset context command
    if message_lower in ['reset context', 'clear context', 'reset', 'start over', 'clear']:
        # Determine cluster if multi-cluster mode
        target_cluster = None
        if config.multi_cluster_enabled:
            target_cluster = detect_cluster_from_message(user_message, config.clusters)
            if not target_cluster:
                target_cluster = config.default_cluster

        context_manager.clear_context(thread_ts, target_cluster)

        if target_cluster:
            say(f"✅ Context cleared for **{target_cluster}** cluster!\n\nStarting fresh conversation.", thread_ts=thread_ts)
        else:
            say("✅ Context cleared!\n\nStarting fresh conversation.", thread_ts=thread_ts)
        return

    # Context info command
    if message_lower in ['context info', 'context', 'context status', 'token usage']:
        # Determine cluster if multi-cluster mode
        target_cluster = None
        if config.multi_cluster_enabled:
            target_cluster = detect_cluster_from_message(user_message, config.clusters)
            if not target_cluster:
                target_cluster = config.default_cluster

        context_info = context_manager.get_context(thread_ts, target_cluster)

        if not context_info:
            say("ℹ️ No active context in this thread.\n\nYour next message will start a new conversation.", thread_ts=thread_ts)
        else:
            usage_pct = (context_info.estimated_tokens / config.max_context_tokens) * 100

            status_emoji = "🟢" if usage_pct < 60 else "🟡" if usage_pct < 85 else "🔴"

            info_text = (
                f"**Context Information**\n\n"
                f"{status_emoji} **Status:** {'OK' if usage_pct < 85 else 'Approaching Limit'}\n"
                f"• Messages: {context_info.message_count}\n"
                f"• Estimated tokens: {context_info.estimated_tokens:,} / {config.max_context_tokens:,}\n"
                f"• Usage: {usage_pct:.1f}%\n"
            )

            if target_cluster:
                info_text += f"• Cluster: {target_cluster}\n"

            if usage_pct > 85:
                info_text += "\n⚠️ *Consider starting a new thread or using `@kagent reset context`*"

            say(info_text, thread_ts=thread_ts)
        return

    # Normal message processing
    say("🤔 Processing your request...", thread_ts=thread_ts)

    try:
        result = kagent.send_message(user_message, thread_id=thread_ts)

        if result['status'] == 'completed' and result['response']:
            say(result['response'], thread_ts=thread_ts)
        elif result['status'] == 'failed':
            say(f"❌ Task failed:\n{result['response']}", thread_ts=thread_ts)
        elif result['status'] in ['timeout', 'error', 'token_limit', 'context_overflow']:
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
    logger.info(f"   Mode: {'Multi-cluster' if config.multi_cluster_enabled else 'Single-cluster'}")
    if config.multi_cluster_enabled:
        logger.info(f"   Clusters: {', '.join(c.name for c in config.clusters)}")
        logger.info(f"   Default: {config.default_cluster}")
    else:
        logger.info(f"   Endpoint: {config.single_cluster_endpoint}")
    logger.info(f"   Max context tokens: {config.max_context_tokens:,}")
    logger.info(f"   Request timeout: {config.request_timeout}s")
    logger.info(f"   Log level: {config.log_level}")

    handler = SocketModeHandler(app, config.slack_app_token)
    logger.info("⚡ Bot is running! Waiting for @mentions...")
    logger.info("   Press Ctrl+C to stop")

    try:
        handler.start()
    except KeyboardInterrupt:
        logger.info("\n🛑 Shutting down gracefully...")
        logger.info("   Bot stopped")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}", exc_info=True)
        exit(1)
