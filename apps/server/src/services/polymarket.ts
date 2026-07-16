import type { Market, MarketDetail, OutcomeEntry, EventSummary } from '../types/index.js';

interface GammaTag {
  label?: string;
  slug?: string;
}

export interface GammaMarket {
  slug?: string;
  question?: string;
  groupItemTitle?: string;
  conditionId?: string;
  volume?: number;
  volumeNum?: number;
  active?: boolean;
  closed?: boolean;
  endDate?: string;
  description?: string;
  image?: string;
  icon?: string;
  // Live pricing fields from Gamma. outcomePrices is usually a JSON-encoded
  // string array (e.g. "[\"0.62\",\"0.38\"]") ordered to match `outcomes`.
  bestBid?: number;
  bestAsk?: number;
  lastTradePrice?: number;
  outcomePrices?: string;
  // Outcome labels as a JSON-encoded string array. Binary markets are
  // '["Yes","No"]'; match/multi-choice markets carry real names, e.g.
  // '["G2","Monte"]' or '["against All authority","INFURITY Gaming"]'.
  outcomes?: string;
  oneDayPriceChange?: number;
  tags?: GammaTag[];
  events?: Array<{ slug?: string; title?: string; image?: string; description?: string }>;
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
type CachedEvent = { data: GammaEvent[]; ts: number };

const CACHE_TTL_MS = 30_000;
// Cache keyed by (offset,limit) so each page is cached independently.
const cache = new Map<string, Cached>();
// Separate cache for event-by-slug lookups (different payload shape).
const eventCache = new Map<string, CachedEvent>();
// Cache for the paged events feed, keyed by (offset,limit).
const eventListCache = new Map<string, CachedEvent>();

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

export interface GammaEvent {
  slug?: string;
  title?: string;
  image?: string;
  icon?: string;
  description?: string;
  volume?: number;
  volumeNum?: number;
  tags?: GammaTag[];
  markets?: GammaMarket[];
}

// Fetch a Polymarket event (with its grouped sub-markets) by event slug. Used
// to surface sibling outcomes on the market detail page.
async function fetchGammaEventBySlug(slug: string): Promise<GammaEvent | null> {
  const now = Date.now();
  const key = `event:${slug}`;
  const hit = eventCache.get(key);
  if (hit && now - hit.ts < CACHE_TTL_MS) return hit.data[0] ?? null;
  try {
    const url =
      `https://gamma-api.polymarket.com/events?slug=${encodeURIComponent(slug)}`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = (await resp.json()) as GammaEvent[];
    eventCache.set(key, { data: json, ts: now });
    return json[0] ?? null;
  } catch (err) {
    if (hit) return hit.data[0] ?? null;
    throw err;
  }
}

// Fetch a page of the Gamma events feed (each event carries its grouped
// sub-markets). Cached per (offset,limit) for 30s, mirroring fetchGammaMarkets.
async function fetchGammaEvents(offset = 0, limit = 30): Promise<GammaEvent[]> {
  const now = Date.now();
  const key = `${offset}:${limit}`;
  const hit = eventListCache.get(key);
  if (hit && now - hit.ts < CACHE_TTL_MS) return hit.data;
  try {
    const url =
      `https://gamma-api.polymarket.com/events?limit=${limit}&offset=${offset}` +
      '&closed=false&order=volume24hr&ascending=false';
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const json = (await resp.json()) as GammaEvent[];
    eventListCache.set(key, { data: json, ts: now });
    return json;
  } catch (err) {
    if (hit) return hit.data;
    throw err;
  }
}

// Internal/operational Gamma tags that should never surface as a user-facing
// category (catch-all buckets, editorial flags, etc.).
const TAG_DENYLIST = new Set([
  'all', 'hide from new', 'recurring', 'new', 'breaking news', 'trending',
]);

// Pull human-readable category labels from a tag list, dropping
// internal/operational tags.
function extractTagLabels(tags: GammaTag[] | undefined): string[] {
  return (tags ?? [])
    .map((t) => (t.label || '').trim())
    .filter((label) => label && !TAG_DENYLIST.has(label.toLowerCase()));
}

// Pull human-readable category labels from the market's tags, dropping
// internal/operational tags.
function extractCategories(m: GammaMarket): string[] {
  return extractTagLabels(m.tags);
}

// Derive the YES probability (0..1) from Gamma's live pricing fields. Prefers
// the quoted outcome price, then the last trade, then the bid/ask midpoint.
// Returns null when no live price is available (so the UI can show "—" rather
// than a misleading fabricated number).
export function deriveYesPrice(m: GammaMarket): number | null {
  if (typeof m.outcomePrices === 'string' && m.outcomePrices.trim()) {
    try {
      const parsed = JSON.parse(m.outcomePrices) as unknown;
      if (Array.isArray(parsed) && parsed.length > 0) {
        const yes = parseFloat(String(parsed[0]));
        if (Number.isFinite(yes)) return yes;
      }
    } catch {
      // Fall through to the other price sources.
    }
  }
  if (typeof m.lastTradePrice === 'number' && Number.isFinite(m.lastTradePrice)) {
    return m.lastTradePrice;
  }
  if (
    typeof m.bestBid === 'number' && Number.isFinite(m.bestBid) &&
    typeof m.bestAsk === 'number' && Number.isFinite(m.bestAsk)
  ) {
    return (m.bestBid + m.bestAsk) / 2;
  }
  return null;
}

// Parse a Gamma JSON-encoded string array (e.g. outcomes / outcomePrices).
// Returns the raw string elements, or an empty array on malformed input.
function parseStringArray(raw: string | undefined): string[] {
  if (typeof raw !== 'string' || !raw.trim()) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) return parsed.map((x) => String(x));
  } catch {
    // Malformed JSON — treat as no data.
  }
  return [];
}

// Pair each outcome label with its corresponding price by index. A label with
// no parseable price (or no price at that index) gets price: null so the UI can
// render "—" rather than a fabricated number.
export function deriveOutcomes(m: GammaMarket): OutcomeEntry[] {
  const labels = parseStringArray(m.outcomes);
  const prices = parseStringArray(m.outcomePrices);
  return labels.map((label, i) => {
    const p = parseFloat(prices[i] ?? '');
    return { label, price: Number.isFinite(p) ? p : null };
  });
}

// A market is binary when its outcomes are exactly ["Yes","No"]
// (case-insensitive, in that order).
export function isBinaryMarket(outcomes: OutcomeEntry[]): boolean {
  return (
    outcomes.length === 2 &&
    outcomes[0].label.trim().toLowerCase() === 'yes' &&
    outcomes[1].label.trim().toLowerCase() === 'no'
  );
}

function normalizeMarket(m: GammaMarket): Market {
  const isLive = m.active === true && m.closed !== true;
  const outcomesList = deriveOutcomes(m);
  return {
    slug: m.slug || '',
    question: m.question || '',
    condition_id: m.conditionId || '',
    volume: m.volumeNum ?? m.volume ?? 0,
    is_live: isLive,
    end_date_iso: m.endDate || null,
    n_holders: null,
    categories: extractCategories(m),
    // Polymarket groups several binary sub-markets under one event. event_slug
    // is the shared event identifier; event_title is the parent event's name
    // (e.g. "What will happen before GTA VI?"); group_title is this sub-market's
    // label (e.g. "50+ bps decrease"). Used to group/label cards in the browser.
    event_slug: m.events?.[0]?.slug || null,
    event_title: m.events?.[0]?.title || null,
    group_title: m.groupItemTitle || null,
    // Card thumbnail (own market image first, then icon).
    icon_url: m.image || m.icon || undefined,
    // Parent event image, used as the event-card thumbnail.
    event_icon: m.events?.[0]?.image || null,
    event_description: m.events?.[0]?.description || null,
    // Live YES probability (0..1) or null when no quote is available.
    yes_price: deriveYesPrice(m),
    // 24h YES price change from Gamma, or null.
    price_change_24h: m.oneDayPriceChange ?? null,
    // Real outcome labels paired with live prices. For binary markets this is
    // [{Yes,..},{No,..}]; for match/multi-choice it holds the actual names.
    outcomes_list: outcomesList,
    // True only when outcomes are exactly ["Yes","No"]. Multi-result markets
    // (team/option names) are false and must not be rendered as Yes/No.
    is_binary: isBinaryMarket(outcomesList),
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
  const subOutcomes = sub?.outcomes ?? [];
  const yes = subOutcomes.find((o) => (o.outcome || '').toLowerCase() === 'yes');
  const no = subOutcomes.find((o) => (o.outcome || '').toLowerCase() === 'no');
  // Real outcome labels + live prices from the top-level Gamma fields.
  const outcomesList = deriveOutcomes(m);
  const binary = isBinaryMarket(outcomesList);
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
    // Real outcome labels when available (e.g. ["G2","Monte"]); fall back to
    // the binary default so existing callers keep a non-empty list.
    outcomes: outcomesList.length > 0 ? outcomesList.map((o) => o.label) : ['Yes', 'No'],
    categories: extractCategories(m),
    icon_url: m.image || m.icon || undefined,
    event_icon: m.events?.[0]?.image || null,
    event_description: m.events?.[0]?.description || null,
    yes_price: deriveYesPrice(m),
    price_change_24h: m.oneDayPriceChange ?? null,
    // Real outcome labels + live prices; is_binary distinguishes Yes/No markets
    // from multi-result (match/multi-choice) ones.
    outcomes_list: outcomesList,
    is_binary: binary,
    // Polymarket groups markets under an event; the event slug is what the
    // public site routes on (polymarket.com/event/<event_slug>).
    event_slug: m.events?.[0]?.slug || null,
    event_title: m.events?.[0]?.title || null,
    group_title: m.groupItemTitle || null,
  };
}

// Map a raw Gamma event into the browse-page EventSummary. Each sub-market
// becomes one outcome row (label = groupItemTitle || question; price = that
// sub-market's YES probability; slug = the sub-market slug). Reuses the shared
// price/outcome parsers so behaviour matches the flat market feed.
export function eventToSummary(ev: GammaEvent): EventSummary {
  const subMarkets = ev.markets ?? [];
  const outcomes = subMarkets.map((m) => ({
    label: m.groupItemTitle || m.question || m.slug || '',
    price: deriveYesPrice(m),
    slug: m.slug || '',
  }));

  // Pick the highest-volume sub-market as the click target (falls back to the
  // first). The detail page then surfaces the rest as siblings.
  let primary = subMarkets[0];
  let primaryVol = (primary?.volumeNum ?? primary?.volume ?? 0) || 0;
  for (const m of subMarkets) {
    const v = (m.volumeNum ?? m.volume ?? 0) || 0;
    if (v > primaryVol) {
      primary = m;
      primaryVol = v;
    }
  }

  // Event volume: prefer the event-level figure, else sum the sub-markets.
  const eventVol = ev.volumeNum ?? ev.volume;
  const volume = typeof eventVol === 'number' && Number.isFinite(eventVol)
    ? eventVol
    : subMarkets.reduce((sum, m) => sum + ((m.volumeNum ?? m.volume ?? 0) || 0), 0);

  // A "single" event is one binary (Yes/No) sub-market — render it as a plain
  // Yes/No card rather than a multi-outcome event card.
  const isSingle =
    subMarkets.length === 1 && isBinaryMarket(deriveOutcomes(subMarkets[0]));

  return {
    event_slug: ev.slug || '',
    title: ev.title || ev.slug || '',
    icon_url: ev.image || ev.icon || undefined,
    description: ev.description || undefined,
    volume,
    categories: extractTagLabels(ev.tags),
    n_outcomes: subMarkets.length,
    primary_slug: primary?.slug || '',
    is_single: isSingle,
    outcomes,
  };
}

// List Polymarket events (server-grouped) for the browse page. Each event keeps
// its sub-markets grouped, so multi-result events (matches, World Cup winner,
// "...by <date>") render as one card instead of flooding the feed with dozens
// of sub-markets. `q` (when set) filters by event title (case-insensitive).
export async function listPolymarketEvents(
  q = '',
  limit = 30,
  offset = 0,
): Promise<EventSummary[]> {
  const events = await fetchGammaEvents(offset, limit);
  const qlower = q.trim().toLowerCase();
  const filtered = qlower
    ? events.filter((ev) => (ev.title || '').toLowerCase().includes(qlower))
    : events;
  return filtered.map(eventToSummary);
}

// Return the sibling sub-markets that belong to the same event, normalized as
// list markets. Used by the detail page to offer outcome switching. Returns an
// empty array for standalone (single-market) events or unknown event slugs.
export async function getPolymarketEventMarkets(eventSlug: string): Promise<Market[]> {
  const event = await fetchGammaEventBySlug(eventSlug);
  if (!event?.markets) return [];
  return event.markets.map((m) => {
    const normalized = normalizeMarket(m);
    // The event payload's sub-markets don't echo the parent event slug, so set
    // it explicitly to keep grouping consistent on the client.
    normalized.event_slug = eventSlug;
    return normalized;
  });
}
