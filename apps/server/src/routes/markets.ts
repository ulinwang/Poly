import type { FastifyInstance } from 'fastify';
import {
  listPolymarketMarkets,
  getPolymarketMarket,
  getPolymarketEventMarkets,
} from '../services/polymarket';

const CATEGORIES = [
  'Trending', 'Breaking', 'Politics', 'Sports', 'Crypto',
  'Esports', 'Tech', 'Culture', 'Economy', 'Weather', 'Elections',
];

export default async function marketsRoutes(app: FastifyInstance) {
  app.get('', async (req, _reply) => {
    const {
      q = '', limit = '30', live_only = '', offset = '0',
    } = req.query as Record<string, string>;
    const limitNum = parseInt(limit, 10) || 30;
    const offsetNum = parseInt(offset, 10) || 0;
    const markets = await listPolymarketMarkets(
      q,
      limitNum,
      live_only === '1' || live_only === 'true',
      offsetNum,
    );
    // Approximate: if the page is full there is likely another page.
    const hasMore = markets.length >= limitNum;
    return { markets, offset: offsetNum, limit: limitNum, hasMore };
  });

  app.get('/categories', async () => {
    return { categories: CATEGORIES };
  });

  // Sibling sub-markets that share an event. Registered before /:slug so the
  // literal "events" segment isn't captured as a market slug.
  app.get('/events/:slug', async (req) => {
    const { slug } = req.params as { slug: string };
    const markets = await getPolymarketEventMarkets(slug);
    return { markets };
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
