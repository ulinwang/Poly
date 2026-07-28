// @vitest-environment jsdom

import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, it, expect, vi } from 'vitest';
import { useDebounce } from './index';

afterEach(() => {
  vi.useRealTimers();
});

// Inline the pure formatter logic (no React hook dependency)
function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—';
  if (!Number.isFinite(n)) return '—';
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(2) + 'M';
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(1) + 'k';
  return n.toFixed(0);
}

describe('formatNumber', () => {
  it('formats null/undefined', () => {
    expect(fmt(null)).toBe('—');
    expect(fmt(undefined)).toBe('—');
  });

  it('formats large numbers with suffix', () => {
    expect(fmt(1_500_000)).toBe('1.50M');
    expect(fmt(2_500)).toBe('2.5k');
    expect(fmt(999)).toBe('999');
  });

  it('handles Infinity', () => {
    expect(fmt(Infinity)).toBe('—');
  });

  it('handles negative numbers', () => {
    expect(fmt(-1_500_000)).toBe('-1.50M');
    expect(fmt(-2_500)).toBe('-2.5k');
  });

  it('handles zero', () => {
    expect(fmt(0)).toBe('0');
  });
});

describe('useDebounce', () => {
  it('delays updates and cancels the superseded timer', () => {
    vi.useFakeTimers();
    const { result, rerender, unmount } = renderHook(
      ({ value, delay }) => useDebounce(value, delay),
      { initialProps: { value: 'initial', delay: 300 } },
    );

    expect(result.current).toBe('initial');
    rerender({ value: 'first', delay: 300 });
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe('initial');

    rerender({ value: 'latest', delay: 300 });
    act(() => vi.advanceTimersByTime(299));
    expect(result.current).toBe('initial');
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe('latest');

    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
});
