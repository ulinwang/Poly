import { describe, it, expect } from 'vitest';
import {
  deriveYesPrice,
  deriveOutcomes,
  isBinaryMarket,
  type GammaMarket,
} from '../services/polymarket';

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

describe('deriveOutcomes', () => {
  it('pairs binary Yes/No labels with their prices', () => {
    const m: GammaMarket = {
      outcomes: '["Yes","No"]',
      outcomePrices: '["0.62","0.38"]',
    };
    expect(deriveOutcomes(m)).toEqual([
      { label: 'Yes', price: 0.62 },
      { label: 'No', price: 0.38 },
    ]);
  });

  it('pairs real team/option labels with their prices (match market)', () => {
    const m: GammaMarket = {
      outcomes: '["G2","Monte"]',
      outcomePrices: '["0.6","0.4"]',
    };
    expect(deriveOutcomes(m)).toEqual([
      { label: 'G2', price: 0.6 },
      { label: 'Monte', price: 0.4 },
    ]);
  });

  it('handles labels with spaces', () => {
    const m: GammaMarket = {
      outcomes: '["against All authority","INFURITY Gaming"]',
      outcomePrices: '["0.55","0.45"]',
    };
    expect(deriveOutcomes(m)).toEqual([
      { label: 'against All authority', price: 0.55 },
      { label: 'INFURITY Gaming', price: 0.45 },
    ]);
  });

  it('uses null price when a label has no parseable price', () => {
    const m: GammaMarket = {
      outcomes: '["A","B","C"]',
      outcomePrices: '["0.5","oops"]',
    };
    expect(deriveOutcomes(m)).toEqual([
      { label: 'A', price: 0.5 },
      { label: 'B', price: null },
      { label: 'C', price: null },
    ]);
  });

  it('returns an empty array when outcomes are absent or malformed', () => {
    expect(deriveOutcomes({})).toEqual([]);
    expect(deriveOutcomes({ outcomes: 'not-json' })).toEqual([]);
  });
});

describe('isBinaryMarket', () => {
  it('is true for exactly Yes/No (case-insensitive)', () => {
    expect(isBinaryMarket(deriveOutcomes({ outcomes: '["Yes","No"]' }))).toBe(true);
    expect(isBinaryMarket(deriveOutcomes({ outcomes: '["yes","NO"]' }))).toBe(true);
  });

  it('is false for team/option markets', () => {
    expect(isBinaryMarket(deriveOutcomes({ outcomes: '["G2","Monte"]' }))).toBe(false);
  });

  it('is false for the reversed No/Yes order', () => {
    expect(isBinaryMarket(deriveOutcomes({ outcomes: '["No","Yes"]' }))).toBe(false);
  });

  it('is false for more than two outcomes', () => {
    expect(isBinaryMarket(deriveOutcomes({ outcomes: '["Yes","No","Maybe"]' }))).toBe(false);
  });

  it('is false when outcomes are missing', () => {
    expect(isBinaryMarket(deriveOutcomes({}))).toBe(false);
  });
});
