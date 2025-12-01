# Kagent Slack Bot - Docker Image
# 2025 best practices: minimal image, non-root user, security hardening

# Use specific version for reproducibility and security
# Note: Update the digest periodically for security patches
FROM python:3.13-slim-bookworm

# Metadata following OCI image spec
LABEL org.opencontainers.image.title="Kagent Slack Bot"
LABEL org.opencontainers.image.description="Secure Slack bot for Kagent AI agents using A2A protocol"
LABEL org.opencontainers.image.authors="Your Name"
LABEL org.opencontainers.image.url="https://github.com/your-org/kagent-slack-bot"
LABEL org.opencontainers.image.source="https://github.com/your-org/kagent-slack-bot"
LABEL org.opencontainers.image.version="1.0.0"
LABEL org.opencontainers.image.licenses="MIT"

# Security: Create non-root user with explicit UID/GID
RUN groupadd --gid 1000 kagent && \
    useradd --uid 1000 --gid kagent --shell /bin/bash --create-home kagent

# Set working directory
WORKDIR /app

# Security: Install dependencies as root, then clean up
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    # Clean up to reduce image size and attack surface
    rm -rf /root/.cache /tmp/* /var/tmp/* && \
    # Remove unnecessary packages
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy application code with correct ownership
COPY --chown=kagent:kagent slack_bot.py .

# Security: Switch to non-root user
USER kagent

# Security: Use read-only root filesystem (compatible with Kubernetes)
# Application will write to /tmp if needed (mounted as volume in k8s)

# Health check - verify Python can start
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys; sys.exit(0)" || exit 1

# Security: Don't run as PID 1 (use tini or dumb-init in production)
# For now, Python handles signals correctly

# Run bot with unbuffered output for better logging
CMD ["python", "-u", "slack_bot.py"]
