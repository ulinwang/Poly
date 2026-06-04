# Backend Dockerfile for the TypeScript Fastify API
# Build context: project root (polymetl/)

FROM node:20-alpine

WORKDIR /app

# Install build tools required for native dependencies (better-sqlite3)
RUN apk add --no-cache python3 make g++

# 1. Copy backend dependency manifests and install all deps (dev + prod) for build
COPY backend/package*.json ./backend/
RUN cd backend && npm ci

# 2. Copy backend source and compile TypeScript
COPY backend/src ./backend/src
COPY backend/tsconfig.json ./backend/
RUN cd backend && npm run build

# 3. Remove dev dependencies to keep the image lean
RUN cd backend && npm prune --production

# 4. Copy pre-built frontend static files so Fastify can serve them
COPY webapp/frontend/dist ./webapp/frontend/dist

# 5. Ensure SQLite data directory exists for volume persistence
RUN mkdir -p /app/backend/data

# Runtime configuration
ENV PORT=8000
ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV DATA_DIR=/app/backend/data

EXPOSE 8000

WORKDIR /app/backend
CMD ["npm", "start"]
