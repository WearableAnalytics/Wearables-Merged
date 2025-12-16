# Build the Vite React app
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies based on the lockfile for reproducible builds
COPY services/web/package*.json ./
RUN npm ci --no-audit --no-fund

# Copy source and build. Override VITE_API_BASE_URL at build time if needed.
COPY services/web ./
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

# Serve the compiled assets with Nginx
FROM nginx:1.27-alpine AS runner
WORKDIR /usr/share/nginx/html
RUN rm -rf ./*

# Custom Nginx config ensures SPA routing works
COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist ./

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
