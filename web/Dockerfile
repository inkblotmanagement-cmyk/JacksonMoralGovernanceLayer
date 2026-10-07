# syntax=docker/dockerfile:1
# JMGL dashboard: build static files with Node, serve them with unprivileged nginx (non-root, port 8080).
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
ARG VITE_API_BASE_URL=
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30-alpine AS runtime
LABEL org.opencontainers.image.title="jmgl-web" \
      org.opencontainers.image.description="JMGL dashboard (static React app)" \
      org.opencontainers.image.licenses="MIT"
# API upstream for same-origin proxying (/v1, /healthz, /readyz) and the browser-visible API base URL.
ENV JMGL_API_UPSTREAM=http://api:8000 \
    JMGL_PUBLIC_API_BASE_URL= \
    NGINX_ENVSUBST_FILTER=^JMGL_ \
    NGINX_ENVSUBST_OUTPUT_DIR=/tmp/conf.d
COPY nginx.conf /etc/nginx/nginx.conf
COPY --chmod=755 05-jmgl-tmpdirs.sh /docker-entrypoint.d/05-jmgl-tmpdirs.sh
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# /config.js is served by nginx from env (exact-match location wins over the static copy).
COPY --from=build /app/dist /usr/share/nginx/html
USER 101
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s CMD wget -qO- http://127.0.0.1:8080/nginx-health >/dev/null || exit 1
