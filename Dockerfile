FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py db.py cfg.py .
ENV PORT=8080
EXPOSE 8080
CMD exec gunicorn -w 1 -b 0.0.0.0:$PORT --timeout 120 "app:app"
