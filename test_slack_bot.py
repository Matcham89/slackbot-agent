"""
Unit tests for Kagent Slack Bot

Tests cover:
- Cluster detection from messages (with aliases)
- Context management (single and multi-cluster)
- Token estimation and limits
- Configuration loading

Note: These tests focus on the core logic functions and classes,
not the full bot initialization which requires Slack credentials.
"""
import unittest
from unittest.mock import Mock, patch, MagicMock
import os
import sys
from dataclasses import dataclass

# Mock environment before importing slack_bot to prevent initialization
os.environ.setdefault('SLACK_BOT_TOKEN', 'xoxb-test-token')
os.environ.setdefault('SLACK_APP_TOKEN', 'xapp-test-token')
os.environ.setdefault('ENABLE_MULTI_CLUSTER', 'false')
os.environ.setdefault('KAGENT_A2A_URL', 'http://localhost:8083/api/a2a/kagent/k8s-agent')

# Import config first
from config import ClusterConfig, BotConfig

# Import only the functions and classes we want to test (not the full module)
# We'll import them individually to avoid running module-level code
import importlib.util
spec = importlib.util.spec_from_file_location("slack_bot_module", "slack_bot.py")
slack_bot_module = importlib.util.module_from_spec(spec)

# Prevent the module from running at import
slack_bot_module.__name__ = "slack_bot_testing"

# Now we can safely get the functions
sys.modules['slack_bot_testing'] = slack_bot_module

# Import only what we need, before the module runs its initialization
import slack_bot
detect_cluster_from_message = slack_bot.detect_cluster_from_message
estimate_tokens = slack_bot.estimate_tokens
ContextManager = slack_bot.ContextManager
ContextInfo = slack_bot.ContextInfo


class TestClusterDetection(unittest.TestCase):
    """Test cluster detection from user messages"""

    def setUp(self):
        """Set up test clusters with aliases"""
        self.clusters = [
            ClusterConfig(
                name="test",
                base_url="http://test.example.com:8080/api/a2a/kagent/k8s-agent/",
                aliases=["testing", "tst", "test-cluster"]
            ),
            ClusterConfig(
                name="dev",
                base_url="http://dev.example.com:8080/api/a2a/kagent/k8s-agent/",
                aliases=["development", "develop", "dev-cluster"]
            ),
            ClusterConfig(
                name="prod",
                base_url="http://prod.example.com:8080/api/a2a/kagent/k8s-agent/",
                aliases=["production", "prd", "prod-cluster"]
            ),
            ClusterConfig(
                name="staging",
                base_url="http://staging.example.com:8080/api/a2a/kagent/k8s-agent/",
                aliases=["stage", "stg"]
            )
        ]

    def test_exact_cluster_name_detection(self):
        """Test detection of exact cluster names"""
        test_cases = [
            ("list pods in test cluster", "test"),
            ("check dev namespace", "dev"),
            ("show prod deployments", "prod"),
            ("what's in staging", "staging"),
        ]

        for message, expected_cluster in test_cases:
            with self.subTest(message=message):
                result = detect_cluster_from_message(message, self.clusters)
                self.assertEqual(result, expected_cluster,
                               f"Failed to detect '{expected_cluster}' in: {message}")

    def test_alias_detection(self):
        """Test detection via cluster aliases"""
        test_cases = [
            ("list pods in testing cluster", "test"),
            ("check development namespace", "dev"),
            ("show production deployments", "prod"),
            ("what's in stage environment", "staging"),
            ("pods in tst", "test"),
            ("namespace on prd", "prod"),
        ]

        for message, expected_cluster in test_cases:
            with self.subTest(message=message):
                result = detect_cluster_from_message(message, self.clusters)
                self.assertEqual(result, expected_cluster,
                               f"Failed to detect '{expected_cluster}' via alias in: {message}")

    def test_case_insensitive_detection(self):
        """Test that detection is case-insensitive"""
        test_cases = [
            ("LIST PODS IN TEST CLUSTER", "test"),
            ("Check DEV namespace", "dev"),
            ("Show PRODUCTION deployments", "prod"),
            ("pods in TeSt", "test"),
        ]

        for message, expected_cluster in test_cases:
            with self.subTest(message=message):
                result = detect_cluster_from_message(message, self.clusters)
                self.assertEqual(result, expected_cluster)

    def test_word_boundary_detection(self):
        """Test that partial matches don't trigger false positives"""
        # These should NOT match
        test_cases = [
            "latest version",  # contains "test" but not as word
            "devops tools",  # contains "dev" but not as word
            "prospect analysis",  # contains "prod" but not as word
        ]

        for message in test_cases:
            with self.subTest(message=message):
                result = detect_cluster_from_message(message, self.clusters)
                self.assertIsNone(result,
                                f"False positive detection in: {message}")

    def test_no_cluster_detected(self):
        """Test cases where no cluster should be detected"""
        test_cases = [
            "list all namespaces",
            "show me the pods",
            "what's the cluster status",
            "kubernetes version",
        ]

        for message in test_cases:
            with self.subTest(message=message):
                result = detect_cluster_from_message(message, self.clusters)
                self.assertIsNone(result)

    def test_multiple_cluster_mentions_first_wins(self):
        """Test that first mentioned cluster is detected"""
        message = "copy from test to prod cluster"
        result = detect_cluster_from_message(message, self.clusters)
        # Should detect "test" since it appears first
        self.assertEqual(result, "test")

    def test_cluster_with_hyphen(self):
        """Test detection of cluster names/aliases with hyphens"""
        message = "check the test-cluster status"
        result = detect_cluster_from_message(message, self.clusters)
        self.assertEqual(result, "test")

    def test_empty_message(self):
        """Test handling of empty message"""
        result = detect_cluster_from_message("", self.clusters)
        self.assertIsNone(result)

    def test_empty_cluster_list(self):
        """Test handling of empty cluster list"""
        result = detect_cluster_from_message("test cluster", [])
        self.assertIsNone(result)


class TestTokenEstimation(unittest.TestCase):
    """Test token estimation functionality"""

    def test_estimate_tokens_basic(self):
        """Test basic token estimation"""
        # Roughly 4 characters per token
        test_cases = [
            ("", 0),
            ("test", 1),
            ("hello world", 2),
            ("a" * 100, 25),
            ("The quick brown fox jumps over the lazy dog", 10),
        ]

        for text, expected_approx in test_cases:
            with self.subTest(text=text[:20]):
                result = estimate_tokens(text)
                # Allow some variance in estimation
                self.assertAlmostEqual(result, expected_approx, delta=2)

    def test_estimate_tokens_multiline(self):
        """Test token estimation for multiline text"""
        text = "Line 1\nLine 2\nLine 3"
        result = estimate_tokens(text)
        # Should count all characters including newlines
        self.assertGreater(result, 0)

    def test_estimate_tokens_unicode(self):
        """Test token estimation with unicode characters"""
        text = "Hello 世界 🌍"
        result = estimate_tokens(text)
        self.assertGreater(result, 0)


class TestContextManager(unittest.TestCase):
    """Test context management functionality"""

    def setUp(self):
        """Set up context manager for tests"""
        self.max_tokens = 10000
        self.manager = ContextManager(max_tokens=self.max_tokens)

    def test_single_cluster_context_creation(self):
        """Test creating context in single-cluster mode"""
        thread_id = "thread-123"
        context_id = "ctx-456"
        message = "test message"
        response = "test response"

        self.manager.set_context(thread_id, context_id, message, response)

        info = self.manager.get_context(thread_id)
        self.assertIsNotNone(info)
        self.assertEqual(info.context_id, context_id)
        self.assertEqual(info.message_count, 1)
        self.assertEqual(info.cluster, None)
        self.assertGreater(info.estimated_tokens, 0)

    def test_single_cluster_context_update(self):
        """Test updating existing context in single-cluster mode"""
        thread_id = "thread-123"
        context_id = "ctx-456"

        # First message
        self.manager.set_context(thread_id, context_id, "msg1", "resp1")
        initial_info = self.manager.get_context(thread_id)

        # Second message (same thread)
        self.manager.set_context(thread_id, context_id, "msg2", "resp2")
        updated_info = self.manager.get_context(thread_id)

        self.assertEqual(updated_info.message_count, 2)
        self.assertGreater(updated_info.estimated_tokens, initial_info.estimated_tokens)

    def test_multi_cluster_context_creation(self):
        """Test creating context in multi-cluster mode"""
        thread_id = "thread-123"
        context_id_test = "ctx-test"
        context_id_dev = "ctx-dev"

        # Message to test cluster
        self.manager.set_context(thread_id, context_id_test, "msg1", "resp1", cluster="test")

        # Message to dev cluster (same thread)
        self.manager.set_context(thread_id, context_id_dev, "msg2", "resp2", cluster="dev")

        # Should have separate contexts
        test_info = self.manager.get_context(thread_id, cluster="test")
        dev_info = self.manager.get_context(thread_id, cluster="dev")

        self.assertIsNotNone(test_info)
        self.assertIsNotNone(dev_info)
        self.assertEqual(test_info.context_id, context_id_test)
        self.assertEqual(dev_info.context_id, context_id_dev)
        self.assertEqual(test_info.cluster, "test")
        self.assertEqual(dev_info.cluster, "dev")

    def test_multi_cluster_context_isolation(self):
        """Test that multi-cluster contexts are isolated per cluster"""
        thread_id = "thread-123"

        # Multiple messages to test cluster
        self.manager.set_context(thread_id, "ctx-test", "msg1", "resp1", cluster="test")
        self.manager.set_context(thread_id, "ctx-test", "msg2", "resp2", cluster="test")

        # Single message to dev cluster
        self.manager.set_context(thread_id, "ctx-dev", "msg3", "resp3", cluster="dev")

        test_info = self.manager.get_context(thread_id, cluster="test")
        dev_info = self.manager.get_context(thread_id, cluster="dev")

        self.assertEqual(test_info.message_count, 2)
        self.assertEqual(dev_info.message_count, 1)

    def test_clear_single_cluster_context(self):
        """Test clearing context in single-cluster mode"""
        thread_id = "thread-123"
        self.manager.set_context(thread_id, "ctx-456", "msg", "resp")

        self.assertIsNotNone(self.manager.get_context(thread_id))

        self.manager.clear_context(thread_id)

        self.assertIsNone(self.manager.get_context(thread_id))

    def test_clear_multi_cluster_specific_context(self):
        """Test clearing specific cluster context in multi-cluster mode"""
        thread_id = "thread-123"
        self.manager.set_context(thread_id, "ctx-test", "msg1", "resp1", cluster="test")
        self.manager.set_context(thread_id, "ctx-dev", "msg2", "resp2", cluster="dev")

        # Clear only test cluster context
        self.manager.clear_context(thread_id, cluster="test")

        self.assertIsNone(self.manager.get_context(thread_id, cluster="test"))
        self.assertIsNotNone(self.manager.get_context(thread_id, cluster="dev"))

    def test_clear_multi_cluster_all_contexts(self):
        """Test clearing all contexts for a thread in multi-cluster mode"""
        thread_id = "thread-123"
        self.manager.set_context(thread_id, "ctx-test", "msg1", "resp1", cluster="test")
        self.manager.set_context(thread_id, "ctx-dev", "msg2", "resp2", cluster="dev")

        # Clear all contexts for thread
        self.manager.clear_context(thread_id)

        self.assertIsNone(self.manager.get_context(thread_id, cluster="test"))
        self.assertIsNone(self.manager.get_context(thread_id, cluster="dev"))

    def test_check_token_limit_under_limit(self):
        """Test token limit check when under limit"""
        thread_id = "thread-123"
        self.manager.set_context(thread_id, "ctx-456", "short", "message")

        over_limit, tokens = self.manager.check_token_limit(thread_id)

        self.assertFalse(over_limit)
        self.assertIsNotNone(tokens)
        self.assertLess(tokens, self.max_tokens)

    def test_check_token_limit_over_limit(self):
        """Test token limit check when over limit"""
        thread_id = "thread-123"
        # Create a very long message that exceeds the limit
        long_message = "x" * (self.max_tokens * 5)  # 5x the limit

        self.manager.set_context(thread_id, "ctx-456", long_message, long_message)

        over_limit, tokens = self.manager.check_token_limit(thread_id)

        self.assertTrue(over_limit)
        self.assertGreater(tokens, self.max_tokens)

    def test_check_token_limit_no_context(self):
        """Test token limit check when no context exists"""
        thread_id = "thread-nonexistent"

        over_limit, tokens = self.manager.check_token_limit(thread_id)

        self.assertFalse(over_limit)
        self.assertIsNone(tokens)

    def test_token_accumulation(self):
        """Test that tokens accumulate over multiple messages"""
        thread_id = "thread-123"
        context_id = "ctx-456"

        # Send multiple messages
        for i in range(5):
            self.manager.set_context(
                thread_id, context_id,
                f"message {i}" * 100,  # Make messages substantial
                f"response {i}" * 100
            )

        info = self.manager.get_context(thread_id)

        self.assertEqual(info.message_count, 5)
        # Tokens should be substantial from 5 messages
        self.assertGreater(info.estimated_tokens, 1000)

    def test_context_none_response(self):
        """Test context management with None response"""
        thread_id = "thread-123"
        self.manager.set_context(thread_id, "ctx-456", "message", None)

        info = self.manager.get_context(thread_id)
        self.assertIsNotNone(info)
        self.assertEqual(info.message_count, 1)
        # Should only count message tokens, not response
        self.assertGreater(info.estimated_tokens, 0)


class TestConfigLoading(unittest.TestCase):
    """Test configuration loading (requires mocking environment)"""

    @patch.dict(os.environ, {
        'SLACK_BOT_TOKEN': 'xoxb-test-token',
        'SLACK_APP_TOKEN': 'xapp-test-token',
        'ENABLE_MULTI_CLUSTER': 'false',
        'KAGENT_A2A_URL': 'http://localhost:8083/api/a2a/kagent/k8s-agent',
    }, clear=True)
    def test_single_cluster_config_loading(self):
        """Test loading single-cluster configuration"""
        from config import load_config

        config = load_config()

        self.assertFalse(config.multi_cluster_enabled)
        self.assertEqual(config.kagent_base_url, 'http://localhost:8083')
        self.assertEqual(config.kagent_namespace, 'kagent')
        self.assertEqual(config.kagent_agent_name, 'k8s-agent')
        self.assertEqual(config.single_cluster_endpoint,
                        'http://localhost:8083/api/a2a/kagent/k8s-agent/')

    @patch.dict(os.environ, {
        'SLACK_BOT_TOKEN': 'xoxb-test-token',
        'SLACK_APP_TOKEN': 'xapp-test-token',
        'ENABLE_MULTI_CLUSTER': 'true',
        'KAGENT_CLUSTERS': 'test,dev',
        'KAGENT_DEFAULT_CLUSTER': 'test',
        'KAGENT_NAMESPACE': 'kagent',
        'KAGENT_AGENT_PATTERN': 'k8s-agent',
        'KAGENT_BASE_URL': 'http://localhost:8080',
    }, clear=True)
    def test_multi_cluster_config_loading(self):
        """Test loading multi-cluster configuration"""
        from config import load_config

        config = load_config()

        self.assertTrue(config.multi_cluster_enabled)
        self.assertEqual(len(config.clusters), 2)
        self.assertEqual(config.default_cluster, 'test')

        # Check cluster configs
        cluster_names = [c.name for c in config.clusters]
        self.assertIn('test', cluster_names)
        self.assertIn('dev', cluster_names)

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_required_secrets(self):
        """Test that missing secrets raises error"""
        from config import load_config

        with self.assertRaises(ValueError) as context:
            load_config()

        self.assertIn("SLACK_BOT_TOKEN", str(context.exception))


class TestContextInfo(unittest.TestCase):
    """Test ContextInfo dataclass"""

    def test_context_info_creation(self):
        """Test creating ContextInfo object"""
        info = ContextInfo(
            context_id="ctx-123",
            cluster="test",
            message_count=5,
            estimated_tokens=1000
        )

        self.assertEqual(info.context_id, "ctx-123")
        self.assertEqual(info.cluster, "test")
        self.assertEqual(info.message_count, 5)
        self.assertEqual(info.estimated_tokens, 1000)

    def test_context_info_none_cluster(self):
        """Test ContextInfo with None cluster (single-cluster mode)"""
        info = ContextInfo(
            context_id="ctx-123",
            cluster=None,
            message_count=1,
            estimated_tokens=100
        )

        self.assertIsNone(info.cluster)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
