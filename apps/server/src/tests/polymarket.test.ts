import { describe, it, expect } from 'vitest';
import { deriveYesPrice, type GammaMarket } from '../services/polymarket';

describe('deriveYesPrice', () => {
  it('parses outcomePrices JSON string (Yes is index 0)', () => {
    const m: GammaMarket = { outcomePrices: '["0.62","0.38"]' };
    expect(deriveYesPrice(m)).toBeCloseTo(0.62);
  });

  it('falls back to lastTradePrice when outcomePrices is absent', () => {
    const m: GammaMarket = { lastTradePrice: 0.41 };
    expect(deriveYesPrice(m)).toBeCloseTo(0.41);
  });

  it('falls back to bid/ask midpoint when no quote or trade', () => {
    const m: GammaMarket = { bestBid: 0.40, bestAsk: 0.50 };
    expect(deriveYesPrice(m)).toBeCloseTo(0.45);
  });

  it('prefers outcomePrices over lastTradePrice and bid/ask', () => {
    const m: GammaMarket = {
      outcomePrices: '["0.70","0.30"]',
      lastTradePrice: 0.41,
      bestBid: 0.40,
      bestAsk: 0.50,
    };
    expect(deriveYesPrice(m)).toBeCloseTo(0.70);
  });

  it('returns null when no price source is available', () => {
    expect(deriveYesPrice({})).toBeNull();
  });

  it('returns null for malformed outcomePrices and no other source', () => {
    expect(deriveYesPrice({ outcomePrices: 'not-json' })).toBeNull();
  });

  it('returns null when only one side of the book is present', () => {
    expect(deriveYesPrice({ bestBid: 0.4 })).toBeNull();
  });
});
