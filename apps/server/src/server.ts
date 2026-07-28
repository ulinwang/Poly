import Fastify from 'fastify';
import cors from '@fastify/cors';
import compress from '@fastify/compress';
import fastifyStatic from '@fastify/static';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import marketsRoutes from './routes/markets.js';
import eventsRoutes from './routes/events.js';
import experimentsRoutes from './routes/experiments.js';
import settingsRoutes from './routes/settings.js';
import keysRoutes from './routes/keys.js';
import providersRoutes from './routes/providers.js';
import agentRoutes from './routes/agent.js';
import analysisRoutes from './routes/analysis.js';
import { repairOrphanedRuns } from './db/experiments.js';
import { config } from './config.js';
import { installAuthentication } from './auth.js';
import type { ExperimentLimits } from './routes/experiments.js';
import type { SpawnOptions, RunHandle } from './services/runner.js';

const isDev = process.env.NODE_ENV === 'development';
const isTest = !!process.env.VITEST || process.env.NODE_ENV === 'test';

export interface BuildServerOptions {
  authRequired?: boolean;
  operatorToken?: string;
  readerToken?: string;
  experimentLimits?: Partial<ExperimentLimits>;
  spawnExperiment?: (
    handle: RunHandle,
    onEvent: (kind: string, data: Record<string, unknown>) => void,
    options?: SpawnOptions,
  ) => void;
}

// Comma-separated list of allowed origins; falls back to the local dev and
// production (nginx) origins used by this project.
const allowedOrigins = (process.env.POLY_CORS_ORIGINS ?? '')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);
if (allowedOrigins.length === 0) {
  allowedOrigins.push('http://localhost:8080', 'http://localhost:5173');
}

export async function buildServer(options: BuildServerOptions = {}) {
  // Repair zombie runs left as 'running' by a previous process that died
  // without finishing them. Paused (resumable) runs are left alone.
  const repaired = repairOrphanedRuns();
  if (repaired > 0) {
    console.warn(`[startup] marked ${repaired} orphaned running experiment(s) as error`);
  }

  const app = Fastify({
    logger: isDev,
  });

  await app.register(compress, { global: true });

  await app.register(cors, {
    origin: (origin, cb) => {
      // Allow same-origin and non-browser requests (no Origin header).
      if (!origin || allowedOrigins.includes(origin)) {
        cb(null, true);
        return;
      }
      cb(new Error('Not allowed by CORS'), false);
    },
    credentials: true,
    allowedHeaders: ['Content-Type', 'Authorization'],
  });

  const operatorToken = options.operatorToken ?? config.API_TOKEN;
  await installAuthentication(app, {
    required: options.authRequired ?? (isTest ? false : !isDev || !!operatorToken.trim()),
    operatorToken,
    readerToken: options.readerToken ?? config.API_READ_TOKEN,
  });

  await app.register(marketsRoutes, { prefix: '/api/v1/markets' });
  await app.register(eventsRoutes, { prefix: '/api/v1/events' });
  await app.register(experimentsRoutes, {
    prefix: '/api/v1/experiments',
    limits: options.experimentLimits,
    spawnRun: options.spawnExperiment,
  });
  await app.register(settingsRoutes, { prefix: '/api/v1/settings' });
  await app.register(keysRoutes, { prefix: '/api/v1/keys' });
  await app.register(providersRoutes, { prefix: '/api/v1/providers' });
  await app.register(agentRoutes, { prefix: '/api/v1/agent' });
  await app.register(analysisRoutes, { prefix: '/api/v1/analysis' });

  const distPath = path.resolve(__dirname, '../../web/dist');
  await app.register(fastifyStatic, {
    root: distPath,
    // wildcard:true serves any file under dist dynamically, so newly-hashed
    // assets after a frontend rebuild are picked up without a server restart.
    wildcard: true,
    maxAge: '1y',
    immutable: true,
  });

  app.setNotFoundHandler((req, reply) => {
    if (req.url.startsWith('/api/')) {
      reply.status(404).send({ message: 'API endpoint not found' });
      return;
    }
    return reply.sendFile('index.html');
  });

  return app;
}
