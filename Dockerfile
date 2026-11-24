FROM python:3.14-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f AS api
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
WORKDIR /app
COPY services/api/requirements-lock.txt /tmp/requirements-lock.txt
RUN pip install --no-cache-dir -r /tmp/requirements-lock.txt && pip check \
    && useradd --uid 10001 --create-home --user-group ain \
    && mkdir -p /app/.local && chown 10001:10001 /app/.local
ARG RELEASE_REVISION=working-tree
LABEL org.opencontainers.image.revision=$RELEASE_REVISION
ENV AIN_RELEASE_REVISION=$RELEASE_REVISION
COPY services services
COPY agents agents
COPY rag rag
COPY optimization optimization
COPY pipelines pipelines
COPY ml ml
COPY infra infra
COPY docs docs
RUN mkdir -p /observer /intake-status
USER 10001:10001
EXPOSE 8002
CMD ["python","-m","uvicorn","services.api.main:app","--host","0.0.0.0","--port","8002","--workers","1","--log-config","infra/request-logging.json","--no-access-log"]

FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS web
WORKDIR /app
RUN addgroup -g 10001 ain && adduser -D -u 10001 -G ain ain
ARG RELEASE_REVISION=working-tree
LABEL org.opencontainers.image.revision=$RELEASE_REVISION
COPY apps/web apps/web
COPY scripts/dev.mjs scripts/api-proxy.mjs scripts/runtime-config.mjs scripts/security-headers.mjs scripts/
USER 10001:10001
EXPOSE 8080
CMD ["node","scripts/dev.mjs"]
