import { describe, it, expect } from 'vitest';

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
});
