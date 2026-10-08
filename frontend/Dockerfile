# syntax=docker/dockerfile:1.7

# ---- build ------------------------------------------------------------------------
FROM node:24-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# Type-check, lint and build: the image only builds from a clean tree.
RUN npm run lint && npm run build

# ---- runtime: static files behind nginx (non-root) --------------------------------
FROM nginxinc/nginx-unprivileged:1.29-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/templates/default.conf.template

ENV API_UPSTREAM=http://backend:8000 \
    TRUSTED_PROXY=127.0.0.1 \
    DNS_RESOLVER=127.0.0.11
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
