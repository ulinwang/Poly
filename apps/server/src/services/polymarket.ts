import type { Market, MarketDetail } from '../types';

interface GammaTag {
  label?: string;
  slug?: string;
}

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
  image?: string;
  icon?: string;
  tags?: GammaTag[];
  events?: Array<{ slug?: string }>;
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
// Cache keyed by (offset,limit) so each page is cached independently.
const cache = new Map<string, Cached>();

async function fetchGammaMarkets(offset = 0, limit = 100): Promise<GammaMarket[]> {
  const now = Date.now();
  const key = `${offset}:${limit}`;
  const hit = cache.get(key);
  if (hit && now - hit.ts < CACHE_TTL_MS) return hit.data;
  try {
    const url =
      `https://gamma-api.polymarket.com/markets?limit=${limit}&offset=${offset}` +
      '&include_tag=true&closed=false&order=volume24hr&ascending=false';
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = (await resp.json()) as GammaMarket[];
    cache.set(key, { data: json, ts: now });
    return json;
  } catch (err) {
    if (hit) return hit.data;
    throw err;
  }
}

// Fetch a single market by its slug directly from Gamma. This is robust to
// pagination/ordering — the paged feed only holds a window of markets, so a
// detail lookup must query by slug rather than search a cached page.
async function fetchGammaMarketBySlug(slug: string): Promise<GammaMarket | null> {
  const now = Date.now();
  const key = `slug:${slug}`;
  const hit = cache.get(key);
  if (hit && now - hit.ts < CACHE_TTL_MS) return hit.data[0] ?? null;
  try {
    const url =
      `https://gamma-api.polymarket.com/markets?slug=${encodeURIComponent(slug)}&include_tag=true`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = (await resp.json()) as GammaMarket[];
    cache.set(key, { data: json, ts: now });
    return json[0] ?? null;
  } catch (err) {
    if (hit) return hit.data[0] ?? null;
    throw err;
  }
}

// Internal/operational Gamma tags that should never surface as a user-facing
// category (catch-all buckets, editorial flags, etc.).
const TAG_DENYLIST = new Set([
  'all', 'hide from new', 'recurring', 'new', 'breaking news', 'trending',
]);

// Pull human-readable category labels from the market's tags, dropping
// internal/operational tags.
function extractCategories(m: GammaMarket): string[] {
  return (m.tags ?? [])
    .map((t) => (t.label || '').trim())
    .filter((label) => label && !TAG_DENYLIST.has(label.toLowerCase()));
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
    categories: extractCategories(m),
  };
}

export async function listPolymarketMarkets(
  q = '',
  limit = 30,
  liveOnly = false,
  offset = 0,
): Promise<Market[]> {
  const markets = await fetchGammaMarkets(offset, limit);
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
  const m = await fetchGammaMarketBySlug(slug);
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
    categories: extractCategories(m),
    icon_url: m.image || m.icon || undefined,
    // Polymarket groups markets under an event; the event slug is what the
    // public site routes on (polymarket.com/event/<event_slug>).
    event_slug: m.events?.[0]?.slug || null,
  };
}
