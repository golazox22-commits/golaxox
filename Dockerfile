FROM python:3.11-slim
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN git clone --depth 1 https://github.com/fashn-AI/fashn-vton-1.5.git /tmp/fashn-repo 2>&1 || true
RUN if [ -d /tmp/fashn-repo ]; then \
        cd /tmp/fashn-repo && pip install --no-cache-dir -e . 2>&1 || \
        pip install --no-cache-dir fashn-vton 2>&1 || true; \
        rm -rf /tmp/fashn-repo; \
    fi
RUN mkdir -p /app/weights
COPY server.py .
ENV FASHN_HOME=/app/weights
ENV PORT=8080
ENV TRYON_DEV=0
EXPOSE 8080
CMD if [ "$TRYON_DEV" = "1" ]; then \
        echo "Starting in DEV mode" && \
        python3 -m flask --app server run --host 0.0.0.0 --port 8080; \
    else \
        echo "Starting with gunicorn" && \
        exec gunicorn -w 1 -b 0.0.0.0:8080 --timeout 600 "server:app"; \
    fi
