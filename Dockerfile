FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser \
    && apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
COPY src ./src
COPY README.md ./README.md
COPY . /workspace
COPY docker-entrypoint.sh /usr/local/bin/agent-entrypoint
RUN chmod 755 /usr/local/bin/agent-entrypoint \
    && rm -rf /workspace/.git /workspace/.github /workspace/.env /workspace/.env.* \
    && cd /workspace \
    && git init --quiet \
    && git config user.email "workspace-index@localhost" \
    && git config user.name "Workspace Index" \
    && git add -A \
    && git commit --quiet -m "Deploy workspace snapshot" \
    && git remote add origin https://github.com/VadimChudin/1010100111101V.git \
    && mkdir -p /app/data /data \
    && chown -R appuser:appuser /app /workspace /data
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/agent-entrypoint"]
