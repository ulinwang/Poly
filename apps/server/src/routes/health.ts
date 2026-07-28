import type { FastifyInstance } from 'fastify';
import fs from 'node:fs';
import { config } from '../config.js';
import { db } from '../db/index.js';

export default async function healthRoutes(app: FastifyInstance) {
  app.get('/live', async () => ({ status: 'ok' }));

  app.get('/ready', async (req, reply) => {
    try {
      db.prepare('SELECT 1').get();
      fs.accessSync(config.DATA_DIR, fs.constants.R_OK | fs.constants.W_OK);
      return { status: 'ready' };
    } catch (error) {
      req.log.error(
        { err: error instanceof Error ? { name: error.name } : { name: 'UnknownError' } },
        'readiness check failed',
      );
      return reply.status(503).send({ status: 'not_ready' });
    }
  });
}
