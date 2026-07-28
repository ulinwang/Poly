import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { EventLogWriter } from './event-log.js';

const tempDirectories: string[] = [];

function temporaryDirectory(): string {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'poly-event-log-'));
  tempDirectories.push(directory);
  return directory;
}

afterEach(() => {
  for (const directory of tempDirectories.splice(0)) {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

describe('EventLogWriter', () => {
  it.each([
    { agents: 20, ticks: 24 },
    { agents: 100, ticks: 200 },
  ])(
    'persists ordered load for $agents agents x $ticks ticks with bounded queue memory',
    async ({ agents, ticks }) => {
      const filePath = path.join(temporaryDirectory(), 'runs', 'load.ndjson');
      const maxPendingBytes = 8 * 1024 * 1024;
      const writer = new EventLogWriter('load', filePath, {
        maxBytes: 32 * 1024 * 1024,
        maxPendingBytes,
      });

      let sequence = 0;
      for (let tick = 0; tick < ticks; tick += 1) {
        for (let agent = 0; agent < agents; agent += 1) {
          expect(writer.append('agent_decision', { tick, agent, sequence })).toBe(true);
          sequence += 1;
        }
      }
      await writer.close();

      const lines = fs.readFileSync(filePath, 'utf8').trim().split('\n');
      expect(lines).toHaveLength(agents * ticks);
      expect(lines.map((line) => JSON.parse(line).data.sequence)).toEqual(
        Array.from({ length: agents * ticks }, (_, index) => index),
      );
      const snapshot = writer.snapshot();
      expect(snapshot.peak_queued_bytes).toBeLessThanOrEqual(maxPendingBytes);
      expect(snapshot.queued_bytes).toBe(0);
      expect(snapshot.dropped_events).toBe(0);
    },
    15_000,
  );

  it('bounds the pending queue and closes without throwing', async () => {
    const filePath = path.join(temporaryDirectory(), 'bounded.ndjson');
    const writer = new EventLogWriter('bounded', filePath, {
      maxBytes: 1_024 * 1_024,
      maxPendingBytes: 256,
    });

    for (let index = 0; index < 100; index += 1) {
      writer.append('large', { index, payload: 'x'.repeat(80) });
    }
    await writer.close();

    const snapshot = writer.snapshot();
    expect(snapshot.status).toBe('limited');
    expect(snapshot.reason).toBe('pending_queue_limit');
    expect(snapshot.peak_queued_bytes).toBeLessThanOrEqual(256);
    expect(snapshot.dropped_events).toBeGreaterThan(0);
  });

  it('surfaces filesystem failure as degraded without crashing the caller', async () => {
    const directory = temporaryDirectory();
    const blocker = path.join(directory, 'not-a-directory');
    fs.writeFileSync(blocker, 'file');
    const logger = { warn: vi.fn(), error: vi.fn() };
    const writer = new EventLogWriter('broken', path.join(blocker, 'run.ndjson'), { logger });

    expect(() => writer.append('tick', { tick: 1 })).not.toThrow();
    await expect(writer.close()).resolves.toBeUndefined();
    expect(writer.snapshot()).toMatchObject({
      status: 'degraded',
      reason: 'filesystem_write_failed',
    });
    expect(logger.error).toHaveBeenCalledTimes(1);
  });
});

