FROM python:3.11-slim

# Bothost ВАЖНО: /app монтируется с хоста при деплое (bind mount),
# поэтому WORKDIR должен быть /usr/src/app — иначе наш код перезапишется.
WORKDIR /usr/src/app

# Системные зависимости (нужны для cryptography, numpy, pandas)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# /app/data — персистентная папка Bothost (сохраняется между деплоями)
RUN mkdir -p /app/data

ENV PORT=3000
# ULTRA_LOW_MEMORY=1 — только 2 модели (HGB+MLP), пик ~30-40 MB.
# Обязательно для Bothost с ограниченным RAM (предотвращает OOM crash loop).
ENV ULTRA_LOW_MEMORY=1
EXPOSE 3000

# Health check: Bothost nginx начнёт роутить трафик только когда /health отвечает 200
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Gunicorn: 1 воркер + 4 треда — обязательно для Flask-SocketIO (async_mode=threading).
# 4 треда вместо 8: каждый тред держит стек ~8MB, экономим ~32MB RAM.
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "1", "--worker-class", "gthread", "--threads", "4", "--timeout", "120", "main:app"]
