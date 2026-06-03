import type { Market, MarketDetail } from '../types';

interface GammaMarket {
  slug?: string;
  question?: string;
  conditionId?: string;
  volume?: number;
  volumeNum?: number;
  active?: boolean;
  closed?: boolean;
  endDate?: string;
  description?: string;
  markets?: Array<{
    minimumTickSize?: number;
    takerBaseFee?: number;
    outcomes?: Array<{
      outcome?: string;
      token_id?: string;
    }>;
  }>;
}

type Cached = { data: GammaMarket[]; ts: number };

const CACHE_TTL_MS = 30_000;
let cache: Cached | null = null;

async function fetchGammaMarkets(): Promise<GammaMarket[]> {
  const now = Date.now();
  if (cache && now - cache.ts < CACHE_TTL_MS) return cache.data;
  try {
    const resp = await fetch('https://gamma-api.polymarket.com/markets?limit=100');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = (await resp.json()) as GammaMarket[];
    cache = { data: json, ts: now };
    return json;
  } catch (err) {
    if (cache) return cache.data;
    throw err;
  }
}

function normalizeMarket(m: GammaMarket): Market {
  const isLive = m.active === true && m.closed !== true;
  return {
    slug: m.slug || '',
    question: m.question || '',
    condition_id: m.conditionId || '',
    volume: m.volumeNum ?? m.volume ?? 0,
    is_live: isLive,
    end_date_iso: m.endDate || null,
    n_holders: null,
    categories: [],
  };
}

export async function listPolymarketMarkets(
  q = '',
  limit = 30,
  liveOnly = false,
): Promise<Market[]> {
  const markets = await fetchGammaMarkets();
  const qlower = q.toLowerCase();
  const filtered = markets.filter((m) => {
    const slug = (m.slug || '').toLowerCase();
    const question = (m.question || '').toLowerCase();
    const matches = !qlower || slug.includes(qlower) || question.includes(qlower);
    const live = m.active === true && m.closed !== true;
    return matches && (!liveOnly || live);
  });
  return filtered.slice(0, limit).map(normalizeMarket);
}

export async function getPolymarketMarket(slug: string): Promise<MarketDetail | null> {
  const markets = await fetchGammaMarkets();
  const m = markets.find((x) => x.slug === slug);
  if (!m) return null;
  const sub = m.markets?.[0];
  const tick = sub?.minimumTickSize ?? 0.01;
  const fee = sub?.takerBaseFee ?? 0;
  const outcomes = sub?.outcomes ?? [];
  const yes = outcomes.find((o) => (o.outcome || '').toLowerCase() === 'yes');
  const no = outcomes.find((o) => (o.outcome || '').toLowerCase() === 'no');
  return {
    slug: m.slug || '',
    question: m.question || '',
    condition_id: m.conditionId || '',
    volume: m.volumeNum ?? m.volume ?? 0,
    is_live: m.active === true && m.closed !== true,
    end_date_iso: m.endDate || null,
    n_holders: null,
    tick_size: typeof tick === 'number' ? tick : parseFloat(tick as unknown as string) || 0.01,
    taker_fee_bps: typeof fee === 'number' ? fee : parseFloat(fee as unknown as string) || 0,
    description: m.description || '',
    yes_token_id: yes?.token_id || '',
    no_token_id: no?.token_id || '',
    outcomes: ['Yes', 'No'],
  };
}
