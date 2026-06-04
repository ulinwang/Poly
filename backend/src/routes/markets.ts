import type { FastifyInstance } from 'fastify';
import { listPolymarketMarkets, getPolymarketMarket } from '../services/polymarket';

const CATEGORIES = [
  'Trending', 'Breaking', 'Politics', 'Sports', 'Crypto',
  'Esports', 'Tech', 'Culture', 'Economy', 'Weather', 'Elections',
];

export default async function marketsRoutes(app: FastifyInstance) {
  app.get('', async (req, _reply) => {
    const { q = '', limit = '30', live_only = '' } = req.query as Record<string, string>;
    const markets = await listPolymarketMarkets(
      q,
      parseInt(limit, 10) || 30,
      live_only === '1' || live_only === 'true',
    );
    return { markets };
  });

  app.get('/categories', async () => {
    return { categories: CATEGORIES };
  });

  app.get('/:slug', async (req, reply) => {
    const { slug } = req.params as { slug: string };
    const market = await getPolymarketMarket(slug);
    if (!market) {
      reply.status(404);
      return { message: 'Market not found' };
    }
    return { market };
  });
}
