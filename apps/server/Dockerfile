# Backend Dockerfile for the TypeScript Fastify API
# Build context: project root. NOTE: this image builds the TS server and serves
# the pre-built web bundle only; it does NOT include the Python sim core, so live
# experiment runs won't work here. Not verified end-to-end after the monorepo
# move — treat as a starting point.

FROM node:20-alpine

WORKDIR /app

# Install build tools required for native dependencies (better-sqlite3)
RUN apk add --no-cache python3 make g++

# 1. Copy server dependency manifests and install all deps (dev + prod) for build
COPY apps/server/package*.json ./apps/server/
RUN cd apps/server && npm ci

# 2. Copy server source and compile TypeScript
COPY apps/server/src ./apps/server/src
COPY apps/server/tsconfig.json ./apps/server/
RUN cd apps/server && npm run build

# 3. Remove dev dependencies to keep the image lean
RUN cd apps/server && npm prune --production

# 4. Copy pre-built frontend static files so Fastify can serve them
#    (server resolves dist at ../../web/dist relative to apps/server/src)
COPY apps/web/dist ./apps/web/dist

# 5. Ensure SQLite data directory exists for volume persistence
RUN mkdir -p /app/apps/server/data

# Runtime configuration
ENV PORT=8765
ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV DATA_DIR=/app/apps/server/data

EXPOSE 8765

WORKDIR /app/apps/server
CMD ["npm", "start"]
