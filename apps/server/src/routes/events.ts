import type { FastifyInstance } from 'fastify';
import { listPolymarketEvents } from '../services/polymarket';

// Browse-page feed: Polymarket events grouped server-side. Each event keeps its
// sub-markets together so multi-result events (matches, multi-candidate races,
// "...by <date>") render as a single card. The flat /markets routes are kept
// unchanged for the detail/analysis views.
export default async function eventsRoutes(app: FastifyInstance) {
  app.get('', async (req) => {
    const { q = '', limit = '30', offset = '0' } =
      req.query as Record<string, string>;
    const limitNum = parseInt(limit, 10) || 30;
    const offsetNum = parseInt(offset, 10) || 0;
    const events = await listPolymarketEvents(q, limitNum, offsetNum);
    // Approximate: if the page came back full there is likely another page.
    const hasMore = events.length >= limitNum;
    return { events, offset: offsetNum, limit: limitNum, hasMore };
  });
}
