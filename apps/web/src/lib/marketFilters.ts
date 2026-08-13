import type { EventSummary } from '../types';

export const ALL_MARKETS_CATEGORY = 'All';

export interface CategoryOption {
  key: string;
  label: string;
  count: number;
}

export function normalizeCategory(value: string): string {
  return value.trim().toLocaleLowerCase();
}

/**
 * Build stable category options from the loaded feed. Labels that differ only
 * by case or surrounding whitespace are combined, and an event is counted at
 * most once per category.
 */
export function deriveCategoryOptions(
  events: EventSummary[],
  limit = 11,
): CategoryOption[] {
  const options = new Map<string, CategoryOption>();

  for (const event of events) {
    const seen = new Set<string>();
    for (const rawLabel of event.categories ?? []) {
      const label = rawLabel.trim();
      const key = normalizeCategory(label);
      if (!key || seen.has(key)) continue;
      seen.add(key);

      const current = options.get(key);
      if (current) current.count += 1;
      else options.set(key, { key, label, count: 1 });
    }
  }

  return [...options.values()]
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
    .slice(0, limit);
}

export function filterEventsByCategory(
  events: EventSummary[],
  category: string,
): EventSummary[] {
  const selected = normalizeCategory(category);
  if (!selected || selected === normalizeCategory(ALL_MARKETS_CATEGORY)) return events;

  return events.filter((event) =>
    (event.categories ?? []).some((label) => normalizeCategory(label) === selected),
  );
}
