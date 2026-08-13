import { describe, expect, it } from 'vitest';
import type { EventSummary } from '../types';
import { deriveCategoryOptions, filterEventsByCategory } from './marketFilters';

function event(event_slug: string, categories: string[]): EventSummary {
  return {
    event_slug,
    title: event_slug,
    icon_url: null,
    volume: 0,
    categories,
    n_outcomes: 1,
    primary_slug: event_slug,
    is_single: true,
    outcomes: [],
  };
}

describe('market category filters', () => {
  const events = [
    event('one', ['Sports', ' Dota 2 ']),
    event('two', ['sports', 'Esports']),
    event('three', ['Politics']),
  ];

  it('combines equivalent labels and reports useful counts', () => {
    expect(deriveCategoryOptions(events)).toEqual([
      { key: 'sports', label: 'Sports', count: 2 },
      { key: 'dota 2', label: 'Dota 2', count: 1 },
      { key: 'esports', label: 'Esports', count: 1 },
      { key: 'politics', label: 'Politics', count: 1 },
    ]);
  });

  it('filters without depending on tag casing or whitespace', () => {
    expect(filterEventsByCategory(events, ' SPORTS ')).toHaveLength(2);
    expect(filterEventsByCategory(events, 'dota 2').map((item) => item.event_slug)).toEqual(['one']);
    expect(filterEventsByCategory(events, 'All')).toBe(events);
  });
});
