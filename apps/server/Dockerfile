# Backend Dockerfile for the TypeScript Fastify API + Python simulation core.
# Builds both the Node server and the web SPA, then bundles the Python venv
# required to spawn sim/runner/runner_cli.py at runtime.

# -----------------------------------------------------------------------------
# Stage 1: Node build (server + SPA)
# -----------------------------------------------------------------------------
FROM node:20-alpine AS node-builder

# better-sqlite3 needs node-gyp (Python) + a C++ toolchain to compile on musl.
RUN apk add --no-cache python3 make g++

WORKDIR /app

# Copy workspace root manifests and lockfile. The root package-lock.json is
# required because apps/server and apps/web are npm workspaces.
COPY package*.json ./
COPY apps/server/package*.json ./apps/server/
COPY apps/web/package*.json ./apps/web/
RUN npm ci

# Copy sources and build both workspaces.
COPY apps/server ./apps/server
COPY apps/web ./apps/web
RUN npm run build --workspace apps/server \
    && npm run build --workspace apps/web

# Prune dev dependencies to keep the runtime image smaller.
RUN cd apps/server && npm prune --production

# -----------------------------------------------------------------------------
# Stage 2: Python venv for the simulation core
# -----------------------------------------------------------------------------
FROM node:20-alpine AS python-builder

# Minimal set for uv + any Python packages that still need compilation on musl.
RUN apk add --no-cache curl python3 python3-dev gcc g++ musl-dev

WORKDIR /app

# Install uv.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy Python project manifest and lockfile.
COPY pyproject.toml uv.lock ./

# Copy the multi-root Python packages referenced by pyproject.toml.
COPY sim ./sim
COPY research ./research
COPY data ./data

# Create a standalone .venv with all production dependencies.
# --frozen ensures uv does not try to update uv.lock inside the build.
# --no-dev skips development-only packages.
RUN uv sync --frozen --no-dev

# -----------------------------------------------------------------------------
# Stage 3: Runtime image
# -----------------------------------------------------------------------------
FROM node:20-alpine AS runtime

# The simulation core needs a Python interpreter at runtime.
RUN apk add --no-cache python3

WORKDIR /app

# Node server artifacts (built in stage 1).
COPY --from=node-builder /app/apps/server/dist ./apps/server/dist
COPY --from=node-builder /app/apps/server/node_modules ./apps/server/node_modules
COPY --from=node-builder /app/apps/server/package.json ./apps/server/package.json
COPY --from=node-builder /app/apps/web/dist ./apps/web/dist
COPY --from=node-builder /app/node_modules ./node_modules
COPY --from=node-builder /app/package.json ./package.json

# Python simulation core artifacts (built in stage 2).
COPY --from=python-builder /app/.venv ./.venv
COPY --from=python-builder /app/sim ./sim
COPY --from=python-builder /app/research ./research
COPY --from=python-builder /app/data ./data
COPY --from=python-builder /app/pyproject.toml ./pyproject.toml

# SQLite data directory (mounted at runtime for persistence).
RUN mkdir -p /app/apps/server/data

ENV PORT=8765
ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV DATA_DIR=/app/apps/server/data
ENV POLY_ROOT=/app

EXPOSE 8765

WORKDIR /app/apps/server
CMD ["node", "dist/index.js"]
