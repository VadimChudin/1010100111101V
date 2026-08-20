FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .
COPY src ./src
COPY README.md ./README.md
COPY docker-entrypoint.sh /usr/local/bin/agent-entrypoint
RUN chmod 755 /usr/local/bin/agent-entrypoint \
    && mkdir -p /workspace /app/data /data \
    && chown -R appuser:appuser /app /workspace /data
EXPOSE 8000
ENTRYPOINT ["/usr/local/bin/agent-entrypoint"]
