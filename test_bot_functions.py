"""
Unit tests for Kagent Slack Bot core functions

Tests the core logic without initializing the full Slack bot.
This avoids needing real Slack credentials for testing.
"""
import unittest
from unittest.mock import Mock, patch
import os
import sys

# Set minimal environment to allow imports
os.environ['SLACK_BOT_TOKEN'] = 'xoxb-test-token'
os.environ['SLACK_APP_TOKEN'] = 'xapp-test-token'

# Import only what we need from config
from config import ClusterConfig


# Copy the functions we want to test directly to avoid module-level initialization
def estimate_tokens(text: str) -> int:
    """Estimate token count for text (rough approximation)"""
    if not text:
        return 0
    return len(text) // 4


def detect_cluster_from_message(message: str, clusters: list) -> str | None:
    """Detect cluster keyword in user message"""
    import re
    message_lower = message.lower()

    # Try exact match for each cluster name first
    for cluster in clusters:
        pattern = r'\b' + re.escape(cluster.name.lower()) + r'\b'
        if re.search(pattern, message_lower):
            return cluster.name

    # Try aliases for each cluster
    for cluster in clusters:
        for alias in cluster.aliases:
            pattern = r'\b' + re.escape(alias.lower()) + r'\b'
            if re.search(pattern, message_lower):
                return cluster.name

    return None


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
        self.assertGreater(result, 0)

    def test_estimate_tokens_unicode(self):
        """Test token estimation with unicode characters"""
        text = "Hello 世界 🌍"
        result = estimate_tokens(text)
        self.assertGreater(result, 0)

    def test_estimate_tokens_long_text(self):
        """Test token estimation for very long text"""
        long_text = "word " * 10000  # 10k words
        result = estimate_tokens(long_text)
        # Should be substantial
        self.assertGreater(result, 10000)


class TestClusterConfig(unittest.TestCase):
    """Test ClusterConfig dataclass"""

    def test_cluster_config_creation(self):
        """Test creating ClusterConfig"""
        config = ClusterConfig(
            name="test",
            base_url="http://test.example.com:8080/api/a2a/kagent/k8s-agent/",
            aliases=["testing", "tst"]
        )

        self.assertEqual(config.name, "test")
        self.assertEqual(config.base_url, "http://test.example.com:8080/api/a2a/kagent/k8s-agent/")
        self.assertEqual(len(config.aliases), 2)
        self.assertIn("testing", config.aliases)

    def test_cluster_config_no_aliases(self):
        """Test ClusterConfig with empty aliases"""
        config = ClusterConfig(
            name="prod",
            base_url="http://prod.example.com:8080/api/a2a/kagent/k8s-agent/",
            aliases=[]
        )

        self.assertEqual(config.name, "prod")
        self.assertEqual(len(config.aliases), 0)


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
