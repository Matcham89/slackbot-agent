"""
Kagent Slack Bot - Intelligent Router Edition

A natural language Slack bot that routes queries to k8s-agents and compares results.

ARCHITECTURE:
1. User asks question in Slack: "@kagent how is my dev cluster"
2. LocalBrain (Ollama) routes the query to the appropriate cluster(s)
3. k8s-agent in each cluster responds with natural language
4. For single cluster: Pass through k8s-agent's response directly
5. For multi-cluster: LocalBrain compares and synthesizes the responses

FEATURES:
- Natural language preservation: k8s-agent responses are not rewritten
- Intelligent routing: Detects which clusters to query
- Multi-cluster comparison: Compares responses when needed
- Conversation context: Maintains thread history

License: MIT
"""
import os
import json
import logging
import hashlib
from typing import Optional, Dict, List
import requests
from sseclient import SSEClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from ollama import Client

# Constants
MAX_DEPLOYMENTS_DISPLAY = 25
RESPONSE_TIMEOUT = 60
DEFAULT_OLLAMA_HOST = 'http://localhost:11434'
DEFAULT_MODEL = 'qwen2.5:14b'

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('slack_bolt').setLevel(logging.INFO)

load_dotenv()

# --- LOCAL BRAIN (REMOTE CONNECTED) ---
class LocalBrain:
    """Handles LLM-based planning and synthesis using Ollama."""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.model = model
        host = os.environ.get('OLLAMA_HOST', DEFAULT_OLLAMA_HOST)
        logger.info(f"🧠 Connecting to Brain at: {host} (Model: {model})")

        # Track which clusters were used in each thread for context-aware routing
        self.thread_cluster_history: Dict[str, List[str]] = {}

        try:
            self.client = Client(host=host)
            # Test connection
            self.client.list()
            logger.info(f"✅ Successfully connected to Ollama at {host}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Ollama at {host}: {e}")
            raise ConnectionError(f"Cannot connect to Ollama at {host}. Ensure Ollama is running.") from e

    def create_execution_plan(self, user_message: str, available_clusters: List[str],
                              thread_id: Optional[str] = None) -> List[Dict[str, str]]:
        """
        MAP STEP: Intelligently routes user queries to the appropriate clusters.
        Returns the ORIGINAL user message to preserve natural language intent.
        Maintains thread context for follow-up questions.
        """
        cluster_list_str = ", ".join(available_clusters) if available_clusters else "none"

        # Get previous clusters used in this thread for context
        previous_clusters = []
        if thread_id and thread_id in self.thread_cluster_history:
            previous_clusters = self.thread_cluster_history[thread_id]
            logger.info(f"🧵 Thread context: Previously used clusters: {previous_clusters}")

        previous_context = ""
        if previous_clusters:
            previous_context = f"\nIMPORTANT: In this conversation thread, the user was previously discussing these clusters: {', '.join(previous_clusters)}. If the current message is a follow-up question (e.g., 'yes continue', 'show me more', 'what about memory'), route to the SAME cluster(s) as before."

        system_prompt = f"""
        You are a Kubernetes cluster router.
        Available Clusters: [{cluster_list_str}]
        {previous_context}

        YOUR TASK:
        1. Identify which clusters the user wants to query based on their message.
        2. Pass the ORIGINAL user question to each cluster (don't modify it).
        3. The k8s-agent in each cluster will handle the natural language interpretation.

        RULES:
        - If user mentions specific cluster names (e.g., "dev", "test", "prod"), include only those.
        - If user says "compare X and Y", include both clusters.
        - If this is a follow-up question (e.g., "yes", "continue", "show more") and previous clusters exist, use those same clusters.
        - If no cluster mentioned and no previous context, use the first available cluster.
        - ALWAYS use the user's original question as the query - don't rewrite it.

        EXAMPLE INPUT: "how is my dev cluster"
        EXAMPLE OUTPUT:
        {{
            "tasks": [
                {{"cluster": "dev", "query": "how is my dev cluster"}}
            ]
        }}

        EXAMPLE INPUT (follow-up): "yes continue" (previous: dev)
        EXAMPLE OUTPUT:
        {{
            "tasks": [
                {{"cluster": "dev", "query": "yes continue"}}
            ]
        }}

        EXAMPLE INPUT: "compare deployments in test and prod"
        EXAMPLE OUTPUT:
        {{
            "tasks": [
                {{"cluster": "test", "query": "compare deployments in test and prod"}},
                {{"cluster": "prod", "query": "compare deployments in test and prod"}}
            ]
        }}

        Return JSON ONLY.
        """

        try:
            logger.info(f"🧠 Routing query with {self.model}...")
            response = self.client.chat(
                model=self.model,
                format='json',
                options={'temperature': 0.0},
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]
            )

            # Robust Parsing
            content = response['message']['content']
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                start = content.find('{')
                end = content.rfind('}') + 1
                data = json.loads(content[start:end]) if start != -1 else {}

            valid_tasks = []
            used_clusters = []
            for task in data.get("tasks", []):
                if task.get("cluster") in available_clusters:
                    valid_tasks.append(task)
                    cluster_name = task.get("cluster")
                    if cluster_name not in used_clusters:
                        used_clusters.append(cluster_name)

            # Update thread history for future context
            if thread_id and used_clusters:
                self.thread_cluster_history[thread_id] = used_clusters
                logger.info(f"🧵 Updated thread {thread_id[:8]}... with clusters: {used_clusters}")

            return valid_tasks

        except Exception as e:
            logger.error(f"🧠 Routing Error: {e}")
            return []

    def synthesize_results(self, user_query: str, results: Dict[str, str]) -> str:
        """
        REDUCE STEP: Only used for multi-cluster comparisons.
        Compares natural language responses from multiple k8s-agents.
        """
        context_text = ""
        for cluster, response in results.items():
            context_text += f"=== Response from '{cluster.upper()}' cluster ===\n{response}\n\n"

        system_prompt = f"""
        You are comparing Kubernetes cluster responses for a user.

        Original Question: "{user_query}"

        Below are natural language responses from different k8s-agents, one per cluster.
        Each agent has already analyzed their cluster and provided a natural response.

        YOUR TASK:
        1. Provide a brief introduction acknowledging you've reviewed all clusters.
        2. Compare and contrast the responses from each cluster.
        3. Highlight key differences (versions, resource counts, configurations, issues).
        4. If clusters are similar, say so clearly.
        5. Use natural, conversational language like a helpful engineer.
        6. Keep it concise and actionable.

        FORMAT GUIDELINES:
        - Start with a natural intro like "I've reviewed both clusters..." or "I've compared the deployments across test and dev..."
        - Use markdown headings for each cluster if helpful (### Test Cluster, ### Dev Cluster)
        - Use *bold* for important differences
        - Use bullet points for lists
        - Keep under 3000 characters

        EXAMPLE TONE:
        "I've reviewed both your test and dev clusters. Here's what I found:

        ### Test Cluster
        - Running 25 deployments across 8 namespaces
        - Kagent version: 0.7.5

        ### Dev Cluster
        - Running 23 deployments across 8 namespaces
        - Kagent version: *0.7.4* (older than test)

        The main difference is that test is running a newer Kagent version (0.7.5 vs 0.7.4)."

        Be conversational and helpful.
        """

        try:
            logger.info(f"🧠 Comparing multi-cluster responses with {self.model}...")
            response = self.client.chat(
                model=self.model,
                options={'temperature': 0.2},  # Slightly higher for natural language
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': context_text},
                ]
            )
            result = response['message']['content']

            # Truncate if too long for Slack
            if len(result) > 3000:
                result = result[:2900] + "\n\n_[Response truncated - too long for Slack]_"

            return result
        except Exception as e:
            logger.error(f"🧠 Synthesis Error: {e}")
            return "⚠️ Error comparing cluster responses."

# --- KAGENT CLIENT (Standard) ---
class KagentClient:
    """Handles communication with Kagent agents via A2A protocol."""

    def __init__(self, base_url: Optional[str] = None, namespace: Optional[str] = None,
                 agent_name: Optional[str] = None, multi_cluster: bool = False,
                 cluster_endpoints: Optional[Dict[str, str]] = None,
                 default_cluster: Optional[str] = None):

        self.multi_cluster = multi_cluster
        if multi_cluster:
            self.cluster_endpoints = cluster_endpoints or {}
            self.clusters = list(cluster_endpoints.keys()) if cluster_endpoints else []
            self.default_cluster = default_cluster or (self.clusters[0] if self.clusters else None)
            self.thread_contexts: Dict[str, Dict[str, str]] = {}
            logger.info(f"🔧 Kagent client initialized (multi-cluster): {', '.join(self.clusters)}")
        else:
            if not all([base_url, namespace, agent_name]):
                raise ValueError("Single-cluster mode requires base_url, namespace, and agent_name")
            self.base_url = base_url
            self.namespace = namespace
            self.agent_name = agent_name
            self.endpoint = f"{base_url}/api/a2a/{namespace}/{agent_name}/"
            self.thread_contexts: Dict[str, str] = {}
            logger.info(f"🔧 Kagent client initialized (single-cluster): {self.endpoint}")

    def _get_endpoint(self, cluster: Optional[str] = None) -> str:
        if self.multi_cluster:
            target = cluster or self.default_cluster
            return self.cluster_endpoints.get(target, "")
        return self.endpoint
    
    def send_message(self, text: str, thread_id: Optional[str] = None, cluster: Optional[str] = None) -> Dict:
        if self.multi_cluster:
            target = cluster or self.default_cluster
            endpoint = self._get_endpoint(target)
        else:
            target = None
            endpoint = self.endpoint

        if not endpoint:
             return {'response': f"Config Error: No endpoint for '{cluster}'", 'status': 'error'}

        logger.info(f"📤 Sending to {target}: {text[:50]}...")
        msg_hash = hashlib.sha256(f"{text}{thread_id}".encode()).hexdigest()[:16]
        
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "message/stream",
            "params": {"message": {"role": "user", "parts": [{"kind": "text", "text": text}], "messageId": f"msg-{msg_hash}"}}
        }

        # Context Management
        context_id = None
        if thread_id:
             if self.multi_cluster and target:
                 if thread_id in self.thread_contexts and target in self.thread_contexts[thread_id]:
                     context_id = self.thread_contexts[thread_id][target]
             elif thread_id in self.thread_contexts:
                 context_id = self.thread_contexts[thread_id]

        if context_id: payload["params"]["message"]["contextId"] = context_id
        
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream", "User-Agent": "kagent-slack-bot/1.0"}
        if os.environ.get("CF_ACCESS_CLIENT_ID"):
            headers["CF-Access-Client-Id"] = os.environ.get("CF_ACCESS_CLIENT_ID")
            headers["CF-Access-Client-Secret"] = os.environ.get("CF_ACCESS_CLIENT_SECRET")

        try:
            # Add timeout to prevent hanging if cluster is slow
            response = requests.post(
                endpoint,
                json=payload,
                headers=headers,
                stream=True,
                timeout=RESPONSE_TIMEOUT,
                verify=True
            )
            response.raise_for_status()
            return self._parse_stream(response, thread_id, target)
        except requests.exceptions.Timeout:
            logger.error(f"⏱️  Request timeout after {RESPONSE_TIMEOUT}s to {endpoint}")
            return {'response': f"⏱️ Request timed out after {RESPONSE_TIMEOUT}s. The cluster may be slow or unreachable.", 'status': 'error'}
        except requests.exceptions.ConnectionError as e:
            logger.error(f"🔌 Connection error to {endpoint}: {e}")
            return {'response': f"🔌 Cannot connect to cluster. Check if Kagent is running.", 'status': 'error'}
        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ HTTP error from {endpoint}: {e}")
            return {'response': f"❌ HTTP error: {e.response.status_code} - {e.response.reason}", 'status': 'error'}
        except Exception as e:
            logger.error(f"⚠️ Unexpected error sending message to {endpoint}: {e}")
            return {'response': f"⚠️ Unexpected error: {str(e)}", 'status': 'error'}

    def _parse_stream(self, response, thread_id: Optional[str], cluster: Optional[str] = None) -> Dict:
        client = SSEClient(response)
        agent_resp = None
        ctx_id = None
        status = "unknown"

        for event in client.events():
            if not event.data.strip(): continue
            try:
                rpc = json.loads(event.data)
                if 'error' in rpc: return {'response': f"Error: {rpc['error'].get('message')}", 'status': 'error'}
                
                res = rpc.get('result', {})
                if 'contextId' in res: 
                    ctx_id = res['contextId']
                    if thread_id:
                        if self.multi_cluster and cluster:
                            if thread_id not in self.thread_contexts: self.thread_contexts[thread_id] = {}
                            self.thread_contexts[thread_id][cluster] = ctx_id
                        else: self.thread_contexts[thread_id] = ctx_id
                
                if 'message' in res.get('status', {}):
                    msg = res['status']['message']
                    if msg.get('role') == 'agent' and msg.get('parts'):
                        agent_resp = msg['parts'][0].get('text', '')
                
                if res.get('final'): break
            except: continue
        return {'response': agent_resp, 'status': status}

# --- SETUP ---
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")
ENABLE_MULTI_CLUSTER = os.environ.get("ENABLE_MULTI_CLUSTER", "false").lower() in ("true", "1", "yes")
KAGENT_CLUSTERS = []
CLUSTER_ENDPOINTS = {}
KAGENT_DEFAULT_CLUSTER = None

if ENABLE_MULTI_CLUSTER:
    KAGENT_CLUSTERS = [c.strip() for c in os.environ.get("KAGENT_CLUSTERS", "").split(",") if c.strip()]
    KAGENT_DEFAULT_CLUSTER = os.environ.get("KAGENT_DEFAULT_CLUSTER", KAGENT_CLUSTERS[0] if KAGENT_CLUSTERS else None)
    pattern = os.environ.get("KAGENT_AGENT_PATTERN")
    if pattern:
        for c in KAGENT_CLUSTERS:
            base = os.environ.get(f"KAGENT_{c.upper()}_BASE_URL", os.environ.get("KAGENT_BASE_URL"))
            agent = pattern.replace("{cluster}", c)
            CLUSTER_ENDPOINTS[c] = f"{base}/api/a2a/{os.environ.get('KAGENT_NAMESPACE')}/{agent}/"
    else:
        for c in KAGENT_CLUSTERS:
            url = os.environ.get(f"KAGENT_{c.upper()}_URL")
            if url: CLUSTER_ENDPOINTS[c] = url

def validate_configuration() -> None:
    """Validate required configuration before starting."""
    if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
        logger.error("❌ Missing SLACK_BOT_TOKEN or SLACK_APP_TOKEN environment variables")
        raise ValueError("SLACK_BOT_TOKEN and SLACK_APP_TOKEN are required")

    if ENABLE_MULTI_CLUSTER:
        if not KAGENT_CLUSTERS:
            logger.error("❌ ENABLE_MULTI_CLUSTER is true but KAGENT_CLUSTERS is empty")
            raise ValueError("KAGENT_CLUSTERS must be set when ENABLE_MULTI_CLUSTER is true")
        if not CLUSTER_ENDPOINTS:
            logger.error("❌ No cluster endpoints configured")
            raise ValueError("Cluster endpoints must be configured for multi-cluster mode")
        logger.info(f"✅ Multi-cluster mode: {len(KAGENT_CLUSTERS)} clusters configured")
    else:
        required = ["KAGENT_BASE_URL", "KAGENT_NAMESPACE", "KAGENT_AGENT_NAME"]
        missing = [var for var in required if not os.environ.get(var)]
        if missing:
            logger.error(f"❌ Missing required environment variables: {', '.join(missing)}")
            raise ValueError(f"Single-cluster mode requires: {', '.join(missing)}")
        logger.info(f"✅ Single-cluster mode: {os.environ.get('KAGENT_BASE_URL')}")


# Validate configuration
validate_configuration()

app = App(token=SLACK_BOT_TOKEN)

local_brain = LocalBrain()

if ENABLE_MULTI_CLUSTER:
    kagent = KagentClient(
        multi_cluster=True,
        cluster_endpoints=CLUSTER_ENDPOINTS,
        default_cluster=KAGENT_DEFAULT_CLUSTER
    )
else:
    kagent = KagentClient(
        base_url=os.environ.get("KAGENT_BASE_URL"),
        namespace=os.environ.get("KAGENT_NAMESPACE"),
        agent_name=os.environ.get("KAGENT_AGENT_NAME")
    )

logger.info("✅ System initialized successfully")

# --- HELPER FUNCTIONS ---
def truncate_if_needed(response: str, max_length: int = 3500) -> str:
    """Truncate response if it exceeds Slack's message limit."""
    if len(response) > max_length:
        return response[:max_length - 100] + "\n\n_[Response truncated due to Slack message limit]_"
    return response


# --- HANDLER ---
@app.event("app_mention")
def handle_mention(event, say, _logger):
    """Handle @mentions in Slack."""
    try:
        thread_ts = event.get("thread_ts") or event.get("ts")
        user_message = event["text"].split(">", 1)[-1].strip()

        if not user_message:
            say("👋 Hi! Ask me about your Kubernetes clusters.", thread_ts=thread_ts)
            return

        # 1. PLAN (Map Phase)
        avail_clusters = KAGENT_CLUSTERS if ENABLE_MULTI_CLUSTER else []

        logger.info(f"📨 Processing: {user_message[:100]}... (thread: {thread_ts[:8]}...)")
        plan = local_brain.create_execution_plan(user_message, avail_clusters, thread_id=thread_ts)

        # Handle General Chat (no clusters detected)
        if not plan:
            if KAGENT_DEFAULT_CLUSTER:
                plan = [{'cluster': KAGENT_DEFAULT_CLUSTER, 'query': user_message}]
            else:
                say(
                    f"👋 I'm up and running! (Brain: {local_brain.model})\n"
                    f"I didn't detect a cluster name in your message. "
                    f"Try asking about '{avail_clusters[0] if avail_clusters else 'dev'}'",
                    thread_ts=thread_ts
                )
                return

        collected_results = {}

        # 2. EXECUTE
        for task in plan:
            cluster = task.get('cluster')
            query = task.get('query')

            # Verify cluster exists before sending
            if cluster and cluster not in KAGENT_CLUSTERS and cluster != KAGENT_DEFAULT_CLUSTER:
                say(f"⚠️ Warning: No endpoint configured for cluster '{cluster}'", thread_ts=thread_ts)
                continue

            cluster_name = cluster or KAGENT_DEFAULT_CLUSTER or "Unknown"

            if len(plan) > 1:
                say(f"🔄 Fetching from *{cluster_name}*...", thread_ts=thread_ts)

            try:
                result = kagent.send_message(query, thread_id=thread_ts, cluster=cluster_name)

                if result['response']:
                    collected_results[cluster_name] = result['response']
                else:
                    collected_results[cluster_name] = "_No data returned._"

                # Check for errors
                if result.get('status') == 'error':
                    logger.warning(f"Error from {cluster_name}: {result['response']}")

            except Exception as e:
                logger.error(f"Exception querying {cluster_name}: {e}")
                collected_results[cluster_name] = f"⚠️ Error: {str(e)}"

        # 3. SYNTHESIZE (only for multi-cluster comparisons)
        if not collected_results:
            say("⚠️ No results collected from clusters.", thread_ts=thread_ts)
            return

        if len(collected_results) > 1:
            # Multiple clusters: compare responses
            say("🧠 Comparing cluster responses...", thread_ts=thread_ts)
            final_answer = local_brain.synthesize_results(user_message, collected_results)
            say(truncate_if_needed(final_answer), thread_ts=thread_ts)
        else:
            # Single cluster: pass through k8s-agent's natural language response directly
            single_key = list(collected_results.keys())[0]
            response = collected_results[single_key]

            # Just truncate if needed, don't reformat - k8s-agent already provides natural language
            say(truncate_if_needed(response), thread_ts=thread_ts)

    except Exception as e:
        logger.error(f"❌ Error in handle_mention: {e}", exc_info=True)
        say(f"⚠️ Sorry, an error occurred: {str(e)}", thread_ts=event.get("thread_ts") or event.get("ts"))

if __name__ == "__main__":
    logger.info(f"🎬 Starting Bot with {local_brain.model}...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    
    try:
        handler.start()
    except KeyboardInterrupt:
        print("\n\n🛑 Bot stopped by user. Exiting...")
        exit(0)