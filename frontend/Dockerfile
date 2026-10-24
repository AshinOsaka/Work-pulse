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
# Sets DNS_RESOLVER from the container's real nameserver at startup, so the /api proxy resolves the backend
# on any platform (Docker's embedded DNS or a host like Render). Runs before the envsubst entrypoint step.
COPY docker-entrypoint.d/15-set-dns-resolver.envsh /docker-entrypoint.d/15-set-dns-resolver.envsh

# DNS_RESOLVER is intentionally left unset: the entrypoint script fills it from the container's own
# nameserver when not provided, and an explicit DNS_RESOLVER (e.g. 8.8.8.8 for a public API URL) is honoured.
ENV API_UPSTREAM=http://backend:8000 \
    TRUSTED_PROXY=127.0.0.1
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -q --spider http://127.0.0.1:8080/healthz || exit 1
