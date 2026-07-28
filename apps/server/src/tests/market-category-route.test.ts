import { afterEach, describe, expect, it, vi } from 'vitest';

const serviceMocks = vi.hoisted(() => ({
  listPolymarketMarkets: vi.fn().mockResolvedValue([]),
  getPolymarketMarket: vi.fn().mockResolvedValue(null),
  getPolymarketEventMarkets: vi.fn().mockResolvedValue([]),
}));

vi.mock('../services/polymarket.js', () => serviceMocks);

import { buildServer } from '../server.js';

afterEach(() => {
  vi.clearAllMocks();
});

describe('market category route', () => {
  it('forwards category alongside search, live-only, limit, and offset', async () => {
    const app = await buildServer();

    const response = await app.inject({
      method: 'GET',
      url: '/api/v1/markets?q=bitcoin&category=cRyPtO&live_only=true&limit=7&offset=14',
    });

    expect(response.statusCode).toBe(200);
    expect(serviceMocks.listPolymarketMarkets).toHaveBeenCalledWith(
      'bitcoin',
      7,
      true,
      14,
      'cRyPtO',
    );

    await app.close();
  });
});
