import type { ServerResponse } from 'node:http';

/**
 * Write one SSE frame while respecting Node's writable high-water mark.
 * Resolves false as soon as the peer disconnects or the response errors.
 */
export function writeSseChunk(response: ServerResponse, chunk: string): Promise<boolean> {
  if (response.destroyed || response.writableEnded) return Promise.resolve(false);
  try {
    if (response.write(chunk)) return Promise.resolve(true);
  } catch {
    return Promise.resolve(false);
  }

  return new Promise((resolve) => {
    const cleanup = () => {
      response.off('drain', onDrain);
      response.off('close', onClosed);
      response.off('error', onClosed);
    };
    const onDrain = () => {
      cleanup();
      resolve(!response.destroyed && !response.writableEnded);
    };
    const onClosed = () => {
      cleanup();
      resolve(false);
    };
    response.once('drain', onDrain);
    response.once('close', onClosed);
    response.once('error', onClosed);
  });
}

export function sseFrame(kind: string, data: Record<string, unknown>): string {
  return `event: ${kind}\ndata: ${JSON.stringify(data)}\n\n`;
}
