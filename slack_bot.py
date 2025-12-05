"""
Kagent Slack Bot - Map-Reduce with Compact Data Strategy

A robust bot that handles large cluster data on small local models (1B).
1. MAP: Asks Agents for "Compact Data" (stripping fluff to save context window).
2. REDUCE: Local Brain compares the compact lists strictly.

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
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger('slack_bolt').setLevel(logging.INFO)

load_dotenv()

# --- LOCAL BRAIN (Compact Orchestrator) ---
class LocalBrain:
    def __init__(self, model='llama3.2:1b'):
        self.model = model

    def create_execution_plan(self, user_message: str, available_clusters: List[str]) -> List[Dict[str, str]]:
        """
        MAP STEP: Generates tasks. 
        CRITICAL: Asks for COMPACT data to prevent overwhelming the 1B model.
        """
        cluster_list_str = ", ".join(available_clusters) if available_clusters else "none"
        
        system_prompt = f"""
        You are a Kubernetes Planner.
        Available Clusters: [{cluster_list_str}]

        YOUR RULES:
        1. Identify which clusters need to be queried.
        2. Create a "List" query for each cluster.
        3. CRITICAL: Instruct the agent to be BRIEF and use a COMPACT list format.
        
        EXAMPLE OUTPUT:
        {{
            "tasks": [
                {{"cluster": "test", "query": "List all deployments in this cluster. Format as: 'Namespace :: DeploymentName :: Image'. Do not add descriptions."}},
                {{"cluster": "dev", "query": "List all deployments in this cluster. Format as: 'Namespace :: DeploymentName :: Image'. Do not add descriptions."}}
            ]
        }}

        Return JSON ONLY.
        """

        try:
            logger.info(f"🧠 Planning with {self.model}...")
            response = ollama.chat(
                model=self.model,
                format='json', 
                options={'temperature': 0.0}, 
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_message},
                ]
            )
            
            # Robust JSON parsing
            content = response['message']['content']
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                start = content.find('{')
                end = content.rfind('}') + 1
                data = json.loads(content[start:end]) if start != -1 else {}

            valid_tasks = []
            for task in data.get("tasks", []):
                if task.get("cluster") in available_clusters:
                    valid_tasks.append(task)
            
            return valid_tasks
            
        except Exception as e:
            logger.error(f"🧠 Plan Error: {e}")
            return []

    def synthesize_results(self, user_query: str, results: Dict[str, str]) -> str:
        """
        REDUCE STEP: Compares compact lists.
        """
        context_text = ""
        for cluster, response in results.items():
            context_text += f"=== DATA FROM CLUSTER '{cluster}' ===\n{response}\n\n"

        system_prompt = f"""
        You are a Kubernetes Auditor.
        User Question: "{user_query}"
        
        Task:
        1. Read the data from the clusters below.
        2. Compare the deployments namespace by namespace.
        3. List EVERY namespace found. Do not skip any.
        4. Highlight differences (e.g. "Namespace X exists in Dev but not Test").

        Keep the final output structured and concise.
        """

        try:
            logger.info(f"🧠 Synthesizing with {self.model}...")
            # We allow a slightly higher temperature for synthesis to make it flow better, 
            # but keep it low for accuracy.
            response = ollama.chat(
                model=self.model,
                options={'temperature': 0.1}, 
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': context_text},
                ]
            )
            return response['message']['content']
        except Exception as e:
            logger.error(f"🧠 Synthesis Error: {e}")
            return "⚠️ I couldn't synthesize the results (data too large). See raw logs below."

# --- KAGENT CLIENT (Standard) ---
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
            response = requests.post(endpoint, json=payload, headers=headers, stream=True, timeout=300, verify=True)
            response.raise_for_status()
            return self._parse_stream(response, thread_id, target)
        except Exception as e:
            return {'response': f"Connection failed: {str(e)}", 'status': 'error'}

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

app = App(token=SLACK_BOT_TOKEN)
local_brain = LocalBrain(model='llama3.2:1b')
if ENABLE_MULTI_CLUSTER:
    kagent = KagentClient(multi_cluster=True, cluster_endpoints=CLUSTER_ENDPOINTS, default_cluster=KAGENT_DEFAULT_CLUSTER)
else:
    kagent = KagentClient(base_url=os.environ.get("KAGENT_BASE_URL"), namespace=os.environ.get("KAGENT_NAMESPACE"), agent_name=os.environ.get("KAGENT_AGENT_NAME"))

logger.info("✅ System initialized (Mode: MAP-REDUCE COMPACT)")

# --- HANDLER ---
@app.event("app_mention")
def handle_mention(event, say, logger):
    thread_ts = event.get("thread_ts") or event.get("ts")
    user_message = event["text"].split(">", 1)[-1].strip()
    if not user_message: return

    # 1. PLAN (Map Phase)
    avail_clusters = KAGENT_CLUSTERS if ENABLE_MULTI_CLUSTER else []
    plan = local_brain.create_execution_plan(user_message, avail_clusters)
    if not plan: plan = [{'cluster': None, 'query': user_message}]

    collected_results = {}
    
    # 2. EXECUTE (Agents do heavy lifting)
    for task in plan:
        cluster = task.get('cluster')
        query = task.get('query')
        cluster_name = cluster or "Default"
        
        if len(plan) > 1:
            say(f"🔄 fetching from *{cluster_name}*...", thread_ts=thread_ts)

        try:
            result = kagent.send_message(query, thread_id=thread_ts, cluster=cluster)
            if result['response']:
                collected_results[cluster_name] = result['response']
            else:
                collected_results[cluster_name] = "No data returned."
        except Exception as e:
            collected_results[cluster_name] = f"Error: {e}"

    # 3. SYNTHESIZE (Reduce Phase)
    if len(collected_results) > 1:
        say("🧠 Analyzing...", thread_ts=thread_ts)
        final_answer = local_brain.synthesize_results(user_message, collected_results)
        
        # SAFETY CHECK: If the 1B model fails to produce a good summary, dump the raw data partially
        if "I couldn't synthesize" in final_answer or len(final_answer) < 50:
             say("⚠️ The data was too large to summarize perfectly. Here is the raw comparison:", thread_ts=thread_ts)
             for c, data in collected_results.items():
                 # Send as code block for better formatting
                 say(f"*{c}*:\n```{data[:1500]}```\n(truncated if too long)", thread_ts=thread_ts)
        else:
             say(final_answer, thread_ts=thread_ts)
    else:
        single_key = list(collected_results.keys())[0]
        say(collected_results[single_key], thread_ts=thread_ts)

if __name__ == "__main__":
    handler = SocketModeHandler(app, SLACK_APP_TOKEN)
    handler.start()