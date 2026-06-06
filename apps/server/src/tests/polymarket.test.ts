import { describe, it, expect } from 'vitest';
import {
  deriveYesPrice,
  deriveOutcomes,
  isBinaryMarket,
  eventToSummary,
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

describe('eventToSummary', () => {
  it('maps a multi-market event to is_single=false with one outcome per sub-market', () => {
    const summary = eventToSummary({
      slug: 'world-cup-winner',
      title: 'World Cup Winner',
      image: 'https://example.com/wc.png',
      tags: [{ label: 'Sports' }, { label: 'Trending' }],
      markets: [
        {
          slug: 'wc-brazil',
          groupItemTitle: 'Brazil',
          outcomes: '["Yes","No"]',
          outcomePrices: '["0.30","0.70"]',
          volumeNum: 500,
        },
        {
          slug: 'wc-argentina',
          groupItemTitle: 'Argentina',
          outcomes: '["Yes","No"]',
          outcomePrices: '["0.25","0.75"]',
          volumeNum: 800,
        },
        {
          slug: 'wc-france',
          groupItemTitle: 'France',
          outcomes: '["Yes","No"]',
          outcomePrices: '["0.20","0.80"]',
          volumeNum: 300,
        },
      ],
    });

    expect(summary.is_single).toBe(false);
    expect(summary.n_outcomes).toBe(3);
    expect(summary.outcomes).toEqual([
      { label: 'Brazil', price: 0.30, slug: 'wc-brazil' },
      { label: 'Argentina', price: 0.25, slug: 'wc-argentina' },
      { label: 'France', price: 0.20, slug: 'wc-france' },
    ]);
    // primary_slug is the highest-volume sub-market (Argentina, 800).
    expect(summary.primary_slug).toBe('wc-argentina');
    expect(summary.categories).toEqual(['Sports']); // "Trending" filtered out.
    expect(summary.icon_url).toBe('https://example.com/wc.png');
  });

  it('falls back to the question and first sub-market when titles/volume are absent', () => {
    const summary = eventToSummary({
      slug: 'multi-no-titles',
      title: 'Multi event',
      markets: [
        { slug: 'a', question: 'Will A happen?', outcomes: '["Yes","No"]', outcomePrices: '["0.5","0.5"]' },
        { slug: 'b', question: 'Will B happen?', outcomes: '["Yes","No"]', outcomePrices: '["0.4","0.6"]' },
      ],
    });
    expect(summary.is_single).toBe(false);
    expect(summary.outcomes[0]).toEqual({ label: 'Will A happen?', price: 0.5, slug: 'a' });
    // No per-market volume → primary falls back to the first sub-market.
    expect(summary.primary_slug).toBe('a');
  });

  it('sums sub-market volume when the event has no event-level volume', () => {
    const summary = eventToSummary({
      slug: 'sum-vol',
      title: 'Sum vol',
      markets: [
        { slug: 'a', groupItemTitle: 'A', outcomes: '["Yes","No"]', volumeNum: 100 },
        { slug: 'b', groupItemTitle: 'B', outcomes: '["Yes","No"]', volumeNum: 250 },
      ],
    });
    expect(summary.volume).toBe(350);
  });

  it('marks a single binary market event as is_single=true', () => {
    const summary = eventToSummary({
      slug: 'will-it-rain',
      title: 'Will it rain tomorrow?',
      volumeNum: 1234,
      markets: [
        {
          slug: 'will-it-rain',
          question: 'Will it rain tomorrow?',
          outcomes: '["Yes","No"]',
          outcomePrices: '["0.62","0.38"]',
        },
      ],
    });
    expect(summary.is_single).toBe(true);
    expect(summary.n_outcomes).toBe(1);
    expect(summary.outcomes[0]).toEqual({ label: 'Will it rain tomorrow?', price: 0.62, slug: 'will-it-rain' });
    expect(summary.primary_slug).toBe('will-it-rain');
    expect(summary.volume).toBe(1234);
  });

  it('treats a single non-binary (multi-result) market event as not single', () => {
    const summary = eventToSummary({
      slug: 'match',
      title: 'G2 vs Monte',
      markets: [
        { slug: 'match', groupItemTitle: 'G2 vs Monte', outcomes: '["G2","Monte"]', outcomePrices: '["0.6","0.4"]' },
      ],
    });
    expect(summary.is_single).toBe(false);
  });
});
