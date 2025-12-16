"""
Configuration management for Kagent Slack Bot

This module separates configuration (non-sensitive) from secrets (sensitive).
Secrets should be loaded from environment variables (Kubernetes secrets, system env, etc.)
Configuration can be loaded from .env file for development.

Security Best Practices:
- NEVER commit .env files with actual tokens
- Use Kubernetes secrets in production
- Use system environment variables for sensitive data
- Keep .env.example as a template only
"""
import os
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from dotenv import load_dotenv

logger = logging.getLogger(__name__)


@dataclass
class ClusterConfig:
    """Configuration for a single cluster in multi-cluster mode"""
    name: str
    base_url: str
    aliases: List[str]


@dataclass
class BotConfig:
    """Complete bot configuration"""
    # Slack credentials (SENSITIVE - from env only)
    slack_bot_token: str
    slack_app_token: str

    # Cloudflare Access (OPTIONAL - from env only)
    cf_access_client_id: Optional[str]
    cf_access_client_secret: Optional[str]

    # Multi-cluster mode
    multi_cluster_enabled: bool

    # Single-cluster config (used when multi_cluster_enabled=False)
    kagent_base_url: Optional[str]
    kagent_namespace: Optional[str]
    kagent_agent_name: Optional[str]

    # Multi-cluster config (used when multi_cluster_enabled=True)
    clusters: List[ClusterConfig]
    default_cluster: Optional[str]

    # Operational settings
    request_timeout: int = 300  # 5 minutes
    max_context_tokens: int = 300000  # Safety margin below 400k
    log_level: str = "INFO"

    @property
    def single_cluster_endpoint(self) -> Optional[str]:
        """Build single-cluster A2A endpoint"""
        if not self.multi_cluster_enabled and all([
            self.kagent_base_url,
            self.kagent_namespace,
            self.kagent_agent_name
        ]):
            return f"{self.kagent_base_url}/api/a2a/{self.kagent_namespace}/{self.kagent_agent_name}/"
        return None


def load_config() -> BotConfig:
    """
    Load configuration from environment variables

    Priority:
    1. System environment variables (highest)
    2. .env file (for local development only)

    Secrets (REQUIRED):
    - SLACK_BOT_TOKEN: Slack bot user OAuth token (xoxb-...)
    - SLACK_APP_TOKEN: Slack app-level token (xapp-...)

    Optional Secrets:
    - CF_ACCESS_CLIENT_ID: Cloudflare Access client ID
    - CF_ACCESS_CLIENT_SECRET: Cloudflare Access client secret

    Configuration (can be in .env):
    - ENABLE_MULTI_CLUSTER: true/false
    - KAGENT_BASE_URL, KAGENT_NAMESPACE, KAGENT_AGENT_NAME (single-cluster)
    - KAGENT_CLUSTERS, KAGENT_DEFAULT_CLUSTER (multi-cluster)
    - REQUEST_TIMEOUT: Request timeout in seconds (default: 300)
    - MAX_CONTEXT_TOKENS: Maximum context size (default: 300000)
    - LOG_LEVEL: Logging level (default: INFO)

    Returns:
        BotConfig: Validated configuration object

    Raises:
        ValueError: If required configuration is missing
    """
    # Load from .env file if exists (dev only - should not contain secrets)
    load_dotenv()

    logger.info("📋 Loading configuration...")

    # Load secrets (MUST be from environment variables)
    slack_bot_token = os.environ.get("SLACK_BOT_TOKEN")
    slack_app_token = os.environ.get("SLACK_APP_TOKEN")

    if not slack_bot_token or not slack_app_token:
        raise ValueError(
            "Missing required secrets: SLACK_BOT_TOKEN and/or SLACK_APP_TOKEN\n"
            "These must be set as environment variables (not in .env file for production)"
        )

    # Optional Cloudflare Access credentials
    cf_access_client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
    cf_access_client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")

    # Operational settings
    request_timeout = int(os.environ.get("REQUEST_TIMEOUT", "300"))
    max_context_tokens = int(os.environ.get("MAX_CONTEXT_TOKENS", "300000"))
    log_level = os.environ.get("LOG_LEVEL", "INFO")

    # Multi-cluster mode
    multi_cluster_enabled = os.environ.get("ENABLE_MULTI_CLUSTER", "false").lower() in ("true", "1", "yes")

    if multi_cluster_enabled:
        clusters, default_cluster = _load_multi_cluster_config()
        logger.info(f"🌐 Multi-cluster mode enabled")
        logger.info(f"   Clusters: {', '.join(c.name for c in clusters)}")
        logger.info(f"   Default: {default_cluster}")

        return BotConfig(
            slack_bot_token=slack_bot_token,
            slack_app_token=slack_app_token,
            cf_access_client_id=cf_access_client_id,
            cf_access_client_secret=cf_access_client_secret,
            multi_cluster_enabled=True,
            kagent_base_url=None,
            kagent_namespace=None,
            kagent_agent_name=None,
            clusters=clusters,
            default_cluster=default_cluster,
            request_timeout=request_timeout,
            max_context_tokens=max_context_tokens,
            log_level=log_level
        )
    else:
        base_url, namespace, agent_name = _load_single_cluster_config()
        logger.info(f"🔧 Single-cluster mode")
        logger.info(f"   Endpoint: {base_url}/api/a2a/{namespace}/{agent_name}/")

        return BotConfig(
            slack_bot_token=slack_bot_token,
            slack_app_token=slack_app_token,
            cf_access_client_id=cf_access_client_id,
            cf_access_client_secret=cf_access_client_secret,
            multi_cluster_enabled=False,
            kagent_base_url=base_url,
            kagent_namespace=namespace,
            kagent_agent_name=agent_name,
            clusters=[],
            default_cluster=None,
            request_timeout=request_timeout,
            max_context_tokens=max_context_tokens,
            log_level=log_level
        )


def _load_single_cluster_config() -> tuple[str, str, str]:
    """Load single-cluster configuration"""
    # Support both configuration styles:
    # 1. KAGENT_A2A_URL (full URL): http://host:port/api/a2a/namespace/agent
    # 2. Separate components: KAGENT_BASE_URL + KAGENT_NAMESPACE + KAGENT_AGENT_NAME

    kagent_a2a_url = os.environ.get("KAGENT_A2A_URL")

    if kagent_a2a_url:
        logger.info(f"   Using KAGENT_A2A_URL: {kagent_a2a_url}")

        if "/api/a2a/" not in kagent_a2a_url:
            raise ValueError(
                "Invalid KAGENT_A2A_URL format. Expected: http://host:port/api/a2a/namespace/agent"
            )

        base_url = kagent_a2a_url.split("/api/a2a/")[0]
        path_parts = kagent_a2a_url.split("/api/a2a/")[1].rstrip("/").split("/")
        namespace = path_parts[0] if len(path_parts) > 0 else None
        agent_name = path_parts[1] if len(path_parts) > 1 else None

        if not all([base_url, namespace, agent_name]):
            raise ValueError("Could not parse KAGENT_A2A_URL into base_url/namespace/agent_name")

        return base_url, namespace, agent_name
    else:
        base_url = os.environ.get("KAGENT_BASE_URL")
        namespace = os.environ.get("KAGENT_NAMESPACE")
        agent_name = os.environ.get("KAGENT_AGENT_NAME")

        if not all([base_url, namespace, agent_name]):
            raise ValueError(
                "Single-cluster mode requires either:\n"
                "  - KAGENT_A2A_URL (full URL), OR\n"
                "  - KAGENT_BASE_URL + KAGENT_NAMESPACE + KAGENT_AGENT_NAME"
            )

        return base_url, namespace, agent_name


def _load_multi_cluster_config() -> tuple[List[ClusterConfig], str]:
    """Load multi-cluster configuration"""
    clusters_str = os.environ.get("KAGENT_CLUSTERS", "")
    cluster_names = [c.strip() for c in clusters_str.split(",") if c.strip()]

    if not cluster_names:
        raise ValueError("Multi-cluster mode enabled but KAGENT_CLUSTERS not provided")

    default_cluster = os.environ.get("KAGENT_DEFAULT_CLUSTER", cluster_names[0])

    if default_cluster not in cluster_names:
        raise ValueError(f"Default cluster '{default_cluster}' not in KAGENT_CLUSTERS")

    # Get namespace (must be same across all clusters)
    namespace = os.environ.get("KAGENT_NAMESPACE")
    if not namespace:
        raise ValueError("Multi-cluster mode requires KAGENT_NAMESPACE")

    # Load cluster configs
    agent_pattern = os.environ.get("KAGENT_AGENT_PATTERN")
    clusters = []

    # Load default cluster aliases
    default_aliases = {
        'prod': ['production', 'prd'],
        'dev': ['development', 'develop'],
        'test': ['testing', 'tst'],
        'stage': ['staging', 'stg'],
        'qa': ['quality', 'qc']
    }

    for cluster_name in cluster_names:
        cluster_upper = cluster_name.upper()

        # Try to get cluster-specific URL first
        cluster_url_var = f"KAGENT_{cluster_upper}_URL"
        cluster_url = os.environ.get(cluster_url_var)

        if cluster_url:
            # Full URL provided
            endpoint = cluster_url
        elif agent_pattern:
            # Pattern-based: build endpoint
            cluster_base_url_var = f"KAGENT_{cluster_upper}_BASE_URL"
            cluster_base_url = os.environ.get(cluster_base_url_var)
            base_url = cluster_base_url if cluster_base_url else os.environ.get("KAGENT_BASE_URL")

            if not base_url:
                raise ValueError(
                    f"Pattern-based routing requires either KAGENT_BASE_URL or {cluster_base_url_var}"
                )

            agent_name = agent_pattern.replace("{cluster}", cluster_name)
            endpoint = f"{base_url}/api/a2a/{namespace}/{agent_name}/"
        else:
            raise ValueError(
                f"No endpoint configured for cluster '{cluster_name}'\n"
                f"Provide either:\n"
                f"  - {cluster_url_var} (full URL), OR\n"
                f"  - KAGENT_AGENT_PATTERN with base URL"
            )

        # Get cluster-specific aliases or use defaults
        aliases_var = f"KAGENT_{cluster_upper}_ALIASES"
        aliases_str = os.environ.get(aliases_var, "")

        if aliases_str:
            # User-provided aliases
            aliases = [a.strip() for a in aliases_str.split(",") if a.strip()]
        else:
            # Use defaults if available
            aliases = default_aliases.get(cluster_name.lower(), [])

        clusters.append(ClusterConfig(
            name=cluster_name,
            base_url=endpoint,
            aliases=aliases
        ))

        logger.info(f"   {cluster_name}: {endpoint}")
        if aliases:
            logger.info(f"      Aliases: {', '.join(aliases)}")

    return clusters, default_cluster


def validate_config(config: BotConfig) -> None:
    """
    Validate configuration after loading

    Raises:
        ValueError: If configuration is invalid
    """
    # Validate tokens format
    if not config.slack_bot_token.startswith("xoxb-"):
        logger.warning("⚠️ SLACK_BOT_TOKEN should start with 'xoxb-'")

    if not config.slack_app_token.startswith("xapp-"):
        logger.warning("⚠️ SLACK_APP_TOKEN should start with 'xapp-'")

    # Validate Cloudflare Access (both or neither)
    if bool(config.cf_access_client_id) != bool(config.cf_access_client_secret):
        raise ValueError(
            "Cloudflare Access requires both CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET"
        )

    # Validate timeouts
    if config.request_timeout < 30 or config.request_timeout > 600:
        raise ValueError("REQUEST_TIMEOUT must be between 30 and 600 seconds")

    # Validate token limits
    if config.max_context_tokens < 10000 or config.max_context_tokens > 400000:
        raise ValueError("MAX_CONTEXT_TOKENS must be between 10000 and 400000")

    logger.info("✅ Configuration validated")
