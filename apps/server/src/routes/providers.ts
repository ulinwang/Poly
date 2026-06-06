import type { FastifyInstance } from 'fastify';
import { providerInfoList } from '../providers';

export default async function providersRoutes(app: FastifyInstance) {
  app.get('', async () => {
    return { providers: providerInfoList() };
  });
}
