FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv git wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

RUN mkdir -p /app/weights
RUN python3 -c "from fashn_vton.scripts.download_weights import main; main()" || \
    (echo "Run: python scripts/download_weights.py --weights-dir /app/weights" && true)

COPY server.py .

ENV FASHN_HOME=/app/weights
ENV PORT=7860
EXPOSE 7860

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:7860", "--timeout", "600", "server:app"]
