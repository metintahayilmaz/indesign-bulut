FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends git nodejs npm \
    && npm install -g @anthropic-ai/claude-code \
    && apt-get clean && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY idmlkit ./idmlkit
COPY server ./server
COPY CLAUDE.md ./
RUN useradd -m app && mkdir -p /data && chown app /data
USER app
ENV DATA_DIR=/data PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
