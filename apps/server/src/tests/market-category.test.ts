import { afterEach, describe, expect, it, vi } from 'vitest';
import { listPolymarketMarkets, type GammaMarket } from '../services/polymarket.js';

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubMarkets(markets: GammaMarket[]) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => markets,
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('market category filtering', () => {
  it('combines a case-insensitive category with query, live-only, limit, and offset', async () => {
    const fetchMock = stubMarkets([
      {
        slug: 'bitcoin-above-100k',
        question: 'Will Bitcoin stay above $100k?',
        active: true,
        closed: false,
        tags: [{ label: 'Crypto' }],
      },
      {
        slug: 'bitcoin-politics',
        question: 'Will Bitcoin become an election issue?',
        active: true,
        closed: false,
        tags: [{ label: 'Politics' }],
      },
      {
        slug: 'bitcoin-inactive',
        question: 'Will Bitcoin remain inactive?',
        active: false,
        closed: false,
        tags: [{ label: 'Crypto' }],
      },
      {
        slug: 'ethereum-price',
        question: 'Will Ethereum rise?',
        active: true,
        closed: false,
        tags: [{ label: 'Crypto' }],
      },
    ]);

    const markets = await listPolymarketMarkets('BITCOIN', 1, true, 42, 'cRyPtO');

    expect(markets.map((market) => market.slug)).toEqual(['bitcoin-above-100k']);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('limit=1&offset=42'));
  });

  it('returns no markets when the requested normalized category is absent', async () => {
    stubMarkets([
      {
        slug: 'election-winner',
        question: 'Who will win the election?',
        active: true,
        closed: false,
        tags: [{ label: 'Politics' }],
      },
    ]);

    await expect(
      listPolymarketMarkets('', 10, false, 43, 'Weather'),
    ).resolves.toEqual([]);
  });

  it('treats the All category as no category filter', async () => {
    stubMarkets([
      {
        slug: 'sports-final',
        question: 'Who will win the final?',
        active: true,
        closed: false,
        tags: [{ label: 'Sports' }],
      },
    ]);

    const markets = await listPolymarketMarkets('', 10, false, 44, 'ALL');

    expect(markets.map((market) => market.slug)).toEqual(['sports-final']);
  });
});
