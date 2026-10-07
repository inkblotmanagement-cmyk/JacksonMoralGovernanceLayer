# syntax=docker/dockerfile:1
# JMGL API image: multi-stage, slim, non-root, embedding model pre-bundled (no network at runtime).
#   docker build -t jmgl-api .
#   docker build --build-arg BUNDLE_MODEL=false -t jmgl-api:rules-only .   # smaller, rules-only fallback
ARG PYTHON_IMAGE=python:3.12-slim-bookworm

FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY pyproject.toml README.md LICENSE CHANGELOG.md ./
COPY src ./src
COPY spec ./spec
COPY eval/model/clf.npz eval/model/clf_meta.json ./eval/model/
RUN pip install --upgrade pip setuptools wheel \
 && pip install ".[server,postgres,redis]" \
 && pip uninstall -y pip setuptools wheel
ARG BUNDLE_MODEL=true
ENV FASTEMBED_CACHE_PATH=/opt/models HF_HUB_DISABLE_TELEMETRY=1
RUN mkdir -p /opt/models && if [ "$BUNDLE_MODEL" = "true" ]; then \
      python -c "from fastembed import TextEmbedding as T; m=T('BAAI/bge-small-en-v1.5'); print(len(list(m.embed(['ok']))[0]))"; \
    fi

FROM ${PYTHON_IMAGE} AS runtime
ARG VERSION=0.5.0
LABEL org.opencontainers.image.title="jmgl-api" \
      org.opencontainers.image.description="Jackson Moral Governance Layer API (pilot-stage)" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.source="https://github.com/inkblotmanagement-cmyk/JacksonMoralGovernanceLayer" \
      org.opencontainers.image.vendor="Mindful Oracle LLC"
RUN groupadd --system --gid 10001 jmgl \
 && useradd --system --uid 10001 --gid jmgl --home-dir /app --no-create-home --shell /usr/sbin/nologin jmgl \
 && mkdir -p /app/data && chown -R 10001:10001 /app \
 && rm -rf /usr/local/lib/python3*/site-packages/pip* /usr/local/bin/pip*
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/models /opt/models
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH=/opt/models HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
    JMGL_ENVIRONMENT=production JMGL_LOG_JSON=true \
    JMGL_AUDIT_DATABASE_URL=sqlite:////app/data/jmgl_audit.db \
    JMGL_AUDIT_FILE_PATH=/app/data/jmgl_audit.jsonl \
    PORT=8000
WORKDIR /app
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD ["python", "-c", "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=4).status == 200 else 1)"]
CMD ["jmgl-server", "serve"]
