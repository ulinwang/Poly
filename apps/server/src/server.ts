import Fastify from 'fastify';
import cors from '@fastify/cors';
import fastifyStatic from '@fastify/static';
import path from 'path';
import { fileURLToPath } from 'url';
// config imported for potential future use

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

import marketsRoutes from './routes/markets';
import experimentsRoutes from './routes/experiments';
import settingsRoutes from './routes/settings';
import keysRoutes from './routes/keys';
import providersRoutes from './routes/providers';
import agentRoutes from './routes/agent';
import analysisRoutes from './routes/analysis';
import { repairOrphanedRuns } from './db/experiments';

const isDev = process.env.NODE_ENV === 'development';

export async function buildServer() {
  // Repair zombie runs left as 'running' by a previous process that died
  // without finishing them. Paused (resumable) runs are left alone.
  const repaired = repairOrphanedRuns();
  if (repaired > 0) {
    console.warn(`[startup] marked ${repaired} orphaned running experiment(s) as error`);
  }

  const app = Fastify({
    logger: isDev,
  });

  await app.register(cors, {
    origin: '*',
    credentials: true,
  });

  await app.register(marketsRoutes, { prefix: '/api/v1/markets' });
  await app.register(experimentsRoutes, { prefix: '/api/v1/experiments' });
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
