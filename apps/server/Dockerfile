# Backend Dockerfile for the TypeScript Fastify API + Python simulation core.
# Builds both the Node server and the web SPA, then bundles the Python venv
# required to spawn sim/runner/runner_cli.py at runtime.

# -----------------------------------------------------------------------------
# Stage 1: Node build (server + SPA)
# -----------------------------------------------------------------------------
FROM node:24-alpine AS node-builder

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
FROM node:24-alpine AS python-builder

# Minimal set for uv + any Python packages that still need compilation on musl
# (e.g. ckzg builds via setuptools' legacy backend, which invokes make).
RUN apk add --no-cache curl python3 python3-dev gcc g++ make musl-dev

WORKDIR /app

# Install uv.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Pin the interpreter to the project's .python-version (3.11) instead of
# whatever Alpine's python3 happens to be — uv installs a managed CPython
# here and the venv links against it, so the runtime stage must copy it too.
ENV UV_PYTHON_INSTALL_DIR=/opt/python

# Copy Python project manifest and lockfile.
COPY pyproject.toml uv.lock .python-version ./

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
FROM node:24-alpine AS runtime

WORKDIR /app

# Node server artifacts (built in stage 1).
COPY --from=node-builder /app/apps/server/dist ./apps/server/dist
COPY --from=node-builder /app/apps/server/package.json ./apps/server/package.json
COPY --from=node-builder /app/apps/web/dist ./apps/web/dist
COPY --from=node-builder /app/node_modules ./node_modules
COPY --from=node-builder /app/package.json ./package.json

# Python simulation core artifacts (built in stage 2). The venv links against
# uv's managed CPython 3.11 (see UV_PYTHON_INSTALL_DIR above), which serves as
# the runtime interpreter — no system python3 needed.
COPY --from=python-builder /opt/python /opt/python
COPY --from=python-builder /app/.venv ./.venv
COPY --from=python-builder /app/sim ./sim
COPY --from=python-builder /app/research ./research
COPY --from=python-builder /app/data ./data
COPY --from=python-builder /app/pyproject.toml ./pyproject.toml

# SQLite/checkpoint/event-log data directory. The named runtime volume inherits
# this ownership on first creation, allowing the backend to stay non-root.
RUN mkdir -p /app/apps/server/data \
    && chown -R node:node /app/apps/server/data

ENV PORT=8765
ENV HOST=0.0.0.0
ENV NODE_ENV=production
ENV DATA_DIR=/app/apps/server/data
ENV POLY_ROOT=/app

EXPOSE 8765

WORKDIR /app/apps/server
USER node
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD node -e "fetch('http://127.0.0.1:8765/api/v1/health/ready').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["node", "dist/index.js"]
