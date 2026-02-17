# Build the Vite React app
FROM node:20-alpine AS builder
WORKDIR /app

# Install dependencies based on the lockfile for reproducible builds
COPY ./package*.json ./

# Cache npm's download cache between builds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --no-audit --no-fund

# Copy source and build.
COPY ./ ./ 
RUN npm run build

# Serve the compiled assets with Nginx
FROM nginx:1.27-alpine AS runner
WORKDIR /usr/share/nginx/html
RUN rm -rf ./*

# Custom Nginx config ensures SPA routing works
COPY ./nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist ./

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
