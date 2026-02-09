# Build the Vite React app
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies based on the lockfile for reproducible builds
COPY ./package*.json ./

# Cache npm's download cache between builds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

# Copy source and build. Override VITE_API_BASE_URL at build time if needed.
COPY ./ ./ 
ARG VITE_BACKEND_URL
ARG VITE_API_BASE_URL
ARG VITE_GRAFANA_PROXY_URL
RUN BUILD_VITE_BACKEND_URL="$VITE_BACKEND_URL" \
  BUILD_VITE_API_BASE_URL="$VITE_API_BASE_URL" \
  BUILD_VITE_GRAFANA_PROXY_URL="$VITE_GRAFANA_PROXY_URL" \
  && if [ -f .env ]; then set -a; . .env; set +a; fi \
  && if [ -n "$BUILD_VITE_BACKEND_URL" ]; then VITE_BACKEND_URL="$BUILD_VITE_BACKEND_URL"; fi \
  && if [ -n "$BUILD_VITE_API_BASE_URL" ]; then VITE_API_BASE_URL="$BUILD_VITE_API_BASE_URL"; fi \
  && if [ -n "$BUILD_VITE_GRAFANA_PROXY_URL" ]; then VITE_GRAFANA_PROXY_URL="$BUILD_VITE_GRAFANA_PROXY_URL"; fi \
  && apiPath="${VITE_API_BASE_URL:-/api}" \
  && case "$apiPath" in */) apiPath="${apiPath%/}";; esac \
  && case "$apiPath" in \
    http://*|https://*) finalApi="$apiPath" ;; \
    *) \
      case "$apiPath" in /*) path="$apiPath" ;; *) path="/$apiPath" ;; esac; \
      if [ -n "$VITE_BACKEND_URL" ]; then finalApi="${VITE_BACKEND_URL%/}${path}"; else finalApi="$path"; fi ;; \
    esac \
  && echo "VITE_API_BASE_URL resolved to $finalApi" \
  && if [ -n "$VITE_GRAFANA_PROXY_URL" ]; then echo "VITE_GRAFANA_PROXY_URL set to $VITE_GRAFANA_PROXY_URL"; else echo "Missing VITE_GRAFANA_PROXY_URL (required)"; exit 1; fi \
  && VITE_API_BASE_URL="$finalApi" npm run build

# Serve the compiled assets with Nginx
FROM nginx:1.27-alpine AS runner
WORKDIR /usr/share/nginx/html
RUN rm -rf ./*

# Custom Nginx config ensures SPA routing works
COPY ./nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist ./

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
