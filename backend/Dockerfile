FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ONNX Runtime and scikit-learn use the OpenMP runtime on Linux.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --requirement /tmp/requirements.txt

RUN groupadd --system --gid 10001 agrisentinel \
    && useradd --system --uid 10001 --gid agrisentinel --home-dir /app agrisentinel

COPY --chown=agrisentinel:agrisentinel backend /app/backend
COPY --chown=agrisentinel:agrisentinel agents /app/agents
COPY --chown=agrisentinel:agrisentinel \
    ml/artifacts/model.onnx \
    ml/artifacts/model_classes.json \
    /app/ml/artifacts/

RUN mkdir -p /app/backend/uploads \
    && chown -R agrisentinel:agrisentinel /app/backend/uploads

USER agrisentinel
WORKDIR /app/backend

EXPOSE 8000
VOLUME ["/app/backend/uploads"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)" || exit 1

# One worker is intentional: live runs and SSE event state are process-local.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips=*"]

