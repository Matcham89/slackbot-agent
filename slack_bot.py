"""
Kagent Slack Bot - A2A Protocol Integration with Local 1B Brain

A secure Slack bot that connects your workspace to Kagent's Kubernetes AI agents.
It uses a lightweight local Ollama model (Llama 3.2 1B) for intelligent routing
and Context Injection to handle multi-cluster comparisons.

License: MIT
"""
import os
import json
import logging
import hashlib
from typing import Optional, Dict, List, Any
import requests
from sseclient import SSEClient
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import ollama 

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise from third-party libraries
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('slack_bolt').setLevel(logging.INFO)

load_dotenv()

# --- LOCAL BRAIN (ROUTER ONLY) ---
class LocalBrain:
    def __init__(self, model='llama3.2:1b'):
        self.model = model

    def analyze_intent(self, user_message: str, available_clusters: List[str]) -> List[str]:
        """
        ROUTER ONLY: Extracts cluster names. 
        Returns a list of target clusters found in the user message.
        """
        cluster_list_str = ", ".join(available_clusters) if available_clusters else "none"
        
        # Simplified prompt: Focus ONLY on extracting names.
        system_prompt = f"""
        You are a Router.
        Valid Clusters: [{cluster_list_str}]

        Task:
        1. Read the user input.
        2. Identify if any "Valid Clusters" are mentioned.
        
        Return JSON ONLY:
        {{
            "target_clusters": ["cluster_name_1", "cluster_name_2"]
        }}
        """

        try:
            logger.info(f"🧠 Routing with {self.model}...")
            # Temperature 0.0 forces the model to be deterministic (essential for JSON)
            response = ollama.chat(
                model=self.model,
                format='json', 
                options={'temperature': 0.0}, 
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]
            )
            
            content = response['message']['content']
            
            # Robust 1B Model JSON Parsing
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Fallback: try to find JSON blob if model chatted a bit
                start = content.find('{')
                end = content.rfind('}') + 1
                if start != -1 and end != -1:
                    data = json.loads(content[start:end])
                else:
                    data = {}

            # Sanitize: Only allow clusters that actually exist in our config
            found_clusters = [c for c in data.get("target_clusters", []) if c in available_clusters]
            
            return found_clusters
            
        except Exception as e:
            logger.error(f"🧠 Brain Error: {e}")
            return []

# --- KAGENT CLIENT ---
class KagentClient:
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
            logger.info(f"🔧 Kagent client initialized (multi-cluster)")
        else:
            self.base_url = base_url
            self.namespace = namespace
            self.agent_name = agent_name
            self.endpoint = f"{base_url}/api/a2a/{namespace}/{agent_name}/"
            self.thread_contexts: Dict[str, str] = {}
            logger.info(f"🔧 Kagent client initialized (single-cluster)")

    def _get_endpoint(self, cluster: Optional[str] = None) -> str:
        if self.multi_cluster:
            target_cluster = cluster or self.default_cluster
            return self.cluster_endpoints.get(target_cluster, "")
        else:
            return self.endpoint
    
    def send_message(self, text: str, thread_id: Optional[str] = None, cluster: Optional[str] = None) -> Dict:
        """Send message to Kagent and extract response from SSE stream"""
        
        if self.multi_cluster:
            target_cluster = cluster or self.default_cluster
            endpoint = self._get_endpoint(target_cluster)
        else:
            target_cluster = None
            endpoint = self.endpoint

        if not endpoint:
             return {'response': f"Config Error: No endpoint for '{cluster}'", 'status': 'error', 'contextId': None}

        # Truncate message in logs for cleanliness
        logger.info(f"📤 Sending to {target_cluster or 'default'} (Thread: {thread_id})")

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

        # Context Management (Thread continuity)
        context_id = None
        if thread_id:
            if self.multi_cluster:
                if thread_id in self.thread_contexts and target_cluster in self.thread_contexts[thread_id]:
                    context_id = self.thread_contexts[thread_id][target_cluster]
            else:
                if thread_id in self.thread_contexts:
                    context_id = self.thread_contexts[thread_id]

        if context_id:
            payload["params"]["message"]["contextId"] = context_id
        
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "kagent-slack-bot/1.0.0"
        }

        # Cloudflare Access support
        if os.environ.get("CF_ACCESS_CLIENT_ID"):
            headers["CF-Access-Client-Id"] = os.environ.get("CF_ACCESS_CLIENT_ID")
            headers["CF-Access-Client-Secret"] = os.environ.get("CF_ACCESS_CLIENT_SECRET")

        try:
            response = requests.post(endpoint, json=payload, headers=headers, stream=True, timeout=300, verify=True)
            response.raise_for_status()
            return self._parse_stream(response, thread_id, target_cluster)
            
        except requests.exceptions.Timeout:
            return {'response': "Request timed out.", 'status': 'timeout', 'contextId': None}
        except requests.exceptions.RequestException as e:
            return {'response': f"Connection failed: {str(e)}", 'status': 'error', 'contextId': None}

    def _parse_stream(self, response, thread_id: Optional[str], cluster: Optional[str] = None) -> Dict:
        client = SSEClient(response)
        agent_response = None
        context_id = None
        status = "unknown"

        for event in client.events():
            if not event.data or not event.data.strip(): continue
            try:
                json_rpc = json.loads(event.data)
                if 'error' in json_rpc:
                    return {'response': f"Agent error: {json_rpc['error'].get('message')}", 'status': 'error'}

                event_data = json_rpc.get('result', {})
                if not event_data: continue

                if 'contextId' in event_data:
                    context_id = event_data['contextId']
                    if thread_id:
                        if self.multi_cluster and cluster:
                            if thread_id not in self.thread_contexts: self.thread_contexts[thread_id] = {}
                            self.thread_contexts[thread_id][cluster] = context_id
                        else:
                            self.thread_contexts[thread_id] = context_id
                
                if 'status' in event_data:
                    status = event_data['status'].get('state', status)
                    if 'message' in event_data['status']:
                        msg = event_data['status']['message']
                        if msg.get('role') == 'agent' and msg.get('parts'):
                            agent_response = msg['parts'][0].get('text', '')
                
                if event_data.get('final'): break
            except Exception:
                continue

        return {'response': agent_response, 'status': status, 'contextId': context_id}

# --- SETUP & CONFIGURATION ---
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN")

# Multi-cluster Config
ENABLE_MULTI_CLUSTER = os.environ.get("ENABLE_MULTI_CLUSTER", "false").lower() in ("true", "1", "yes")
KAGENT_CLUSTERS = []
CLUSTER_ENDPOINTS = {}
KAGENT_DEFAULT_CLUSTER = None
KAGENT_BASE_URL = os.environ.get("KAGENT_BASE_URL")
KAGENT_NAMESPACE = os.environ.get("KAGENT_NAMESPACE")

if ENABLE_MULTI_CLUSTER:
    KAGENT_CLUSTERS = [c.strip() for c in os.environ.get("KAGENT_CLUSTERS", "").split(",") if c.strip()]
    KAGENT_DEFAULT_CLUSTER = os.environ.get("KAGENT_DEFAULT_CLUSTER", KAGENT_CLUSTERS[0] if KAGENT_CLUSTERS else None)
    pattern = os.environ.get("KAGENT_AGENT_PATTERN")
    
    if pattern:
        for c in KAGENT_CLUSTERS:
            # Check for cluster-specific URL, fallback to global base URL
            c_base = os.environ.get(f"KAGENT_{c.upper()}_BASE_URL", KAGENT_BASE_URL)
            agent = pattern.replace("{cluster}", c)
            CLUSTER_ENDPOINTS[c] = f"{c_base}/api/a2a/{KAGENT_NAMESPACE}/{agent}/"
    else:
        for c in KAGENT_CLUSTERS:
            url = os.environ.get(f"KAGENT_{c.upper()}_URL")
            if url: CLUSTER_ENDPOINTS[c] = url

if not SLACK_BOT_TOKEN or not SLACK_APP_TOKEN:
    logger.error("❌ Missing SLACK tokens")
    exit(1)

app = App(token=SLACK_BOT_TOKEN)
# Initialize Brain with Lightweight Model
local_brain = LocalBrain(model='llama3.2:1b')

if ENABLE_MULTI_CLUSTER:
    kagent = KagentClient(multi_cluster=True, cluster_endpoints=CLUSTER_ENDPOINTS, default_cluster=KAGENT_DEFAULT_CLUSTER)
else:
    agent_name = os.environ.get("KAGENT_AGENT_NAME")
    if not KAGENT_BASE_URL and os.environ.get("KAGENT_A2A_URL"):
         KAGENT_A2A_URL = os.environ.get("KAGENT_A2A_URL")
         KAGENT_BASE_URL = KAGENT_A2A_URL.split("/api/a2a/")[0]
         path_parts = KAGENT_A2A_URL.split("/api/a2a/")[1].rstrip("/").split("/")
         KAGENT_NAMESPACE = path_parts[0]
         agent_name = path_parts[1]

    kagent = KagentClient(base_url=KAGENT_BASE_URL, namespace=KAGENT_NAMESPACE, agent_name=agent_name)

logger.info("✅ System initialized")

# --- SLACK HANDLERS ---

@app.event("app_mention")
def handle_mention(event, say, logger):
    """Handle @kagent mentions"""
    thread_ts = event.get("thread_ts") or event.get("ts")
    user_message = event["text"].split(">", 1)[-1].strip()
    
    if not user_message:
        say("Please provide a message!", thread_ts=thread_ts)
        return

    # 1. BRAIN ANALYSIS (Routing Only)
    # We only ask the brain "Where does this go?". We rely on Python for the logic.
    avail_clusters = KAGENT_CLUSTERS if ENABLE_MULTI_CLUSTER else []
    target_clusters = local_brain.analyze_intent(user_message, avail_clusters)
    
    # Fallback to default if no specific cluster mentioned
    if not target_clusters:
        target_clusters = [None] 

    results = []

    # 2. EXECUTION LOOP
    for cluster in target_clusters:
        cluster_name = cluster if cluster else (KAGENT_DEFAULT_CLUSTER if ENABLE_MULTI_CLUSTER else "Default")
        
        # Only notify if comparing multiple clusters
        if len(target_clusters) > 1:
            say(f"🔄 Querying: *{cluster_name}*...", thread_ts=thread_ts)

        # --- CONTEXT INJECTION (The Fix) ---
        # If we are comparing clusters, we must wrap the message so the Agent knows WHO it is.
        if len(target_clusters) > 1:
            # We filter out the CURRENT cluster from the "ignore list"
            other_clusters = [c for c in target_clusters if c != cluster]
            other_clusters_str = ", ".join(other_clusters)
            
            prompt_to_send = (
                f"SYSTEM CONTEXT: You are the '{cluster_name}' cluster. "
                f"The user is asking to compare multiple clusters. "
                f"Ignore references to other clusters (specifically: '{other_clusters_str}'). "
                f"Report strictly on YOUR local status.\n\n"
                f"USER QUERY: {user_message}"
            )
        else:
            # Single cluster: Send raw message to avoid confusing the agent
            prompt_to_send = user_message
        # -----------------------------------

        try:
            result = kagent.send_message(prompt_to_send, thread_id=thread_ts, cluster=cluster)
            
            if result['status'] == 'completed' and result['response']:
                resp = result['response']
                if len(target_clusters) > 1:
                    results.append(f"🏗️ *Cluster: {cluster_name}*\n{resp}")
                else:
                    results.append(resp)
            else:
                 results.append(f"⚠️ *{cluster_name}*: {result.get('response', 'No response')}")

        except Exception as e:
            logger.error(f"❌ Error in loop: {e}")
            results.append(f"❌ Failed to query {cluster_name}")

    # 3. SEND FINAL RESPONSE
    final_output = "\n\n---\n\n".join(results)
    say(final_output, thread_ts=thread_ts)

@app.event("message")
def handle_message_events(body, logger):
    pass 

if __name__ == "__main__":
    logger.info(f"🎬 Starting Bot with {local_brain.model}...")
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()