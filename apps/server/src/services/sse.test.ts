import { ServerResponse } from 'node:http';
import { EventEmitter } from 'node:events';
import { describe, expect, it, vi } from 'vitest';
import { writeSseChunk } from './sse.js';

function responseDouble(writeResult: boolean) {
  return Object.assign(new EventEmitter(), {
    destroyed: false,
    writableEnded: false,
    write: vi.fn(() => writeResult),
  }) as unknown as ServerResponse;
}

describe('writeSseChunk', () => {
  it('waits for drain when the response applies backpressure', async () => {
    const response = responseDouble(false);
    const pending = writeSseChunk(response, 'event: ping\n\n');
    let settled = false;
    void pending.then(() => {
      settled = true;
    });
    await Promise.resolve();
    expect(settled).toBe(false);

    response.emit('drain');
    await expect(pending).resolves.toBe(true);
  });

  it('stops promptly when the peer closes during backpressure', async () => {
    const response = responseDouble(false);
    const pending = writeSseChunk(response, 'event: ping\n\n');
    response.destroyed = true;
    response.emit('close');
    await expect(pending).resolves.toBe(false);
  });

  it('keeps 20-agent x 24-tick frame delivery within the latency budget', async () => {
    const response = responseDouble(true);
    const started = performance.now();
    for (let tick = 0; tick < 24; tick += 1) {
      for (let agent = 0; agent < 20; agent += 1) {
        await writeSseChunk(response, `event: agent_decision\ndata: {"tick":${tick},"agent":${agent}}\n\n`);
      }
    }
    expect(performance.now() - started).toBeLessThan(250);
    expect(response.write).toHaveBeenCalledTimes(20 * 24);
  });
});
