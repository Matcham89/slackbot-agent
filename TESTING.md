# Testing Guide

This guide explains how to test the Kagent Slack Bot.

---

## Running Tests

### Quick Start

```bash
# Create a virtual environment (if you don't have one)
python3 -m venv venv-test

# Activate it
source venv-test/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run all tests
python -m unittest test_bot_functions -v
```

### What Gets Tested

The test suite covers:

✅ **Cluster Detection**
- Exact cluster name matching
- Alias-based detection
- Case-insensitive matching
- Word boundary handling (no false positives)
- Empty inputs and edge cases

✅ **Token Estimation**
- Basic text tokenization
- Multiline text handling
- Unicode character support
- Long text handling

✅ **Configuration**
- ClusterConfig dataclass
- Alias management

---

## Test Files

### `test_bot_functions.py`

Tests core logic functions without requiring Slack credentials:
- `detect_cluster_from_message()` - Cluster routing logic
- `estimate_tokens()` - Token counting for context management
- `ClusterConfig` - Configuration dataclass

**Why this approach?**
- No Slack API credentials needed
- Fast execution (no network calls)
- Focuses on business logic
- Can run in CI/CD pipelines

### `test_slack_bot.py`

Comprehensive tests including:
- Full `ContextManager` class
- Multi-cluster context isolation
- Token limit checking
- Context persistence and clearing

*Note: This requires mocking Slack SDK to avoid API calls*

---

## Test Coverage

### Cluster Detection Tests

```python
# Example test cases
"list pods in test cluster"        →  detects "test"
"check development namespace"      →  detects "dev" (via alias)
"show PRODUCTION deployments"      →  detects "prod" (case-insensitive)
"devops tools"                     →  None (no false positive)
```

### Token Estimation Tests

```python
# Rough heuristic: ~4 chars per token
""                    →  0 tokens
"test"                →  1 token
"hello world"         →  2 tokens
"a" * 100             →  25 tokens
```

### Multi-Cluster Tests

```python
# Separate contexts per cluster
thread "T123" + cluster "test"  →  context_id "ctx-test"
thread "T123" + cluster "dev"   →  context_id "ctx-dev"

# Isolation verified
test cluster: 10 messages, 5000 tokens
dev cluster:  2 messages, 1000 tokens
```

---

## Adding New Tests

### Structure

```python
import unittest
from config import ClusterConfig

class TestMyFeature(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        self.clusters = [
            ClusterConfig(
                name="test",
                base_url="http://test.example.com:8080/...",
                aliases=["testing", "tst"]
            )
        ]

    def test_my_feature(self):
        """Test description"""
        result = my_function(input_data)
        self.assertEqual(result, expected_output)
```

### Best Practices

1. **Use subTest for multiple cases**
   ```python
   for message, expected in test_cases:
       with self.subTest(message=message):
           result = detect_cluster(message, clusters)
           self.assertEqual(result, expected)
   ```

2. **Test edge cases**
   - Empty inputs
   - None values
   - Very long inputs
   - Unicode characters
   - Special characters

3. **Test error conditions**
   ```python
   with self.assertRaises(ValueError):
       function_that_should_fail(bad_input)
   ```

---

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.14'
      - run: pip install -r requirements.txt
      - run: python -m unittest test_bot_functions -v
```

---

## Manual Testing

### Local Development Testing

1. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration

   export SLACK_BOT_TOKEN="xoxb-your-token"
   export SLACK_APP_TOKEN="xapp-your-token"
   ```

2. **Port-forward Kagent (if testing locally):**
   ```bash
   kubectl port-forward -n kagent svc/kagent-controller 8083:8083
   ```

3. **Run the bot:**
   ```bash
   python slack_bot.py
   ```

4. **Test in Slack:**
   ```
   /invite @kagent

   # Test basic functionality
   @kagent help
   @kagent list namespaces

   # Test context management
   @kagent context info
   @kagent reset context

   # Test multi-cluster (if enabled)
   @kagent list pods in test cluster
   @kagent check dev namespace
   ```

### Testing Token Limits

To test token limit handling without waiting for natural accumulation:

1. **Lower the limit temporarily:**
   ```bash
   export MAX_CONTEXT_TOKENS=1000  # Very low limit for testing
   python slack_bot.py
   ```

2. **Generate a long conversation:**
   ```
   @kagent tell me about all the pods in all namespaces with full details
   @kagent now tell me about all the deployments
   @kagent and all the services
   # ... continue until you hit the limit
   ```

3. **Verify error handling:**
   - Should see "Context Too Large" message
   - Should offer to reset context
   - `@kagent reset context` should work

4. **Test context info:**
   ```
   @kagent context info
   ```
   Should show token usage approaching limit

---

## Debugging Tests

### Run specific test

```bash
# Single test class
python -m unittest test_bot_functions.TestClusterDetection -v

# Single test method
python -m unittest test_bot_functions.TestClusterDetection.test_alias_detection -v
```

### Verbose output

```bash
python -m unittest test_bot_functions -v
```

### Stop on first failure

```bash
python -m unittest test_bot_functions --failfast
```

---

## Test Data

### Sample Cluster Configurations

```python
# Test cluster
ClusterConfig(
    name="test",
    base_url="http://test.example.com:8080/api/a2a/kagent/k8s-agent/",
    aliases=["testing", "tst", "test-cluster"]
)

# Dev cluster
ClusterConfig(
    name="dev",
    base_url="http://dev.example.com:8080/api/a2a/kagent/k8s-agent/",
    aliases=["development", "develop", "dev-cluster"]
)

# Prod cluster
ClusterConfig(
    name="prod",
    base_url="http://prod.example.com:8080/api/a2a/kagent/k8s-agent/",
    aliases=["production", "prd", "prod-cluster"]
)
```

### Sample Messages for Testing

```python
# Should detect clusters
messages = [
    "list pods in test cluster",
    "check dev namespace",
    "show production deployments",
    "what's in testing",
    "pods on development",
]

# Should NOT detect clusters (false positives)
messages = [
    "latest version",      # contains "test"
    "devops tools",        # contains "dev"
    "prospect analysis",   # contains "prod"
]
```

---

## Performance Testing

### Token Estimation Performance

```python
import time

def test_token_estimation_performance():
    long_text = "word " * 100000  # 100k words

    start = time.time()
    tokens = estimate_tokens(long_text)
    duration = time.time() - start

    print(f"Estimated {tokens:,} tokens in {duration:.3f}s")
    # Should be < 0.01s for reasonable performance
```

### Cluster Detection Performance

```python
def test_cluster_detection_performance():
    clusters = [ClusterConfig(...) for _ in range(100)]  # Many clusters
    message = "check the test-cluster-99 status"

    start = time.time()
    result = detect_cluster_from_message(message, clusters)
    duration = time.time() - start

    print(f"Detected cluster in {duration:.3f}s")
    # Should be < 0.01s even with many clusters
```

---

## Troubleshooting Tests

### Module import errors

```
ModuleNotFoundError: No module named 'requests'
```

**Solution:**
```bash
source venv-test/bin/activate
pip install -r requirements.txt
```

### Slack API errors during tests

```
SlackApiError: invalid_auth
```

**Solution:**
This means the test is trying to initialize the full Slack bot. Use `test_bot_functions.py` instead of `test_slack_bot.py` for unit tests that don't need Slack.

### Configuration errors

```
ValueError: Missing required secrets: SLACK_BOT_TOKEN
```

**Solution:**
Set mock environment variables:
```bash
export SLACK_BOT_TOKEN="xoxb-test-token"
export SLACK_APP_TOKEN="xapp-test-token"
```

---

## Future Testing Enhancements

Areas for future test coverage:

- [ ] Integration tests with mock Slack API
- [ ] Integration tests with mock Kagent API
- [ ] Performance benchmarks
- [ ] Load testing (many concurrent threads)
- [ ] Context persistence tests (Redis/database)
- [ ] Error recovery tests
- [ ] Network failure scenarios
- [ ] Timeout handling tests

---

## Resources

- [Python unittest documentation](https://docs.python.org/3/library/unittest.html)
- [unittest.mock](https://docs.python.org/3/library/unittest.mock.html)
- [Python testing best practices](https://docs.python-guide.org/writing/tests/)
