import fs from 'node:fs';
import path from 'node:path';
import type { FileHandle } from 'node:fs/promises';
import type { FastifyBaseLogger } from 'fastify';
import { config } from '../config.js';

type Logger = Pick<FastifyBaseLogger, 'warn' | 'error'>;

export type EventLogStatus = 'healthy' | 'limited' | 'degraded' | 'closed';

export interface EventLogSnapshot {
  status: EventLogStatus;
  persisted_bytes: number;
  queued_bytes: number;
  peak_queued_bytes: number;
  dropped_events: number;
  reason: string | null;
}

interface EventLogWriterOptions {
  maxBytes?: number;
  maxPendingBytes?: number;
  logger?: Logger | null;
}

/**
 * Ordered, bounded, asynchronous NDJSON writer.
 *
 * Producers only enqueue strings; a single drain loop batches writes through
 * one file handle. Filesystem failures degrade persistence without throwing
 * into the simulation, and both the file and pending queue have hard bounds.
 */
export class EventLogWriter {
  private readonly maxBytes: number;
  private readonly maxPendingBytes: number;
  private logger: Logger | null;
  private file: FileHandle | null = null;
  private queue: string[] = [];
  private queuedBytes = 0;
  private persistedBytes = 0;
  private peakQueuedBytes = 0;
  private droppedEvents = 0;
  private status: EventLogStatus = 'healthy';
  private reason: string | null = null;
  private drainPromise: Promise<void> | null = null;
  private closePromise: Promise<void> | null = null;
  private closing = false;

  constructor(
    readonly runId: string,
    readonly filePath: string,
    options: EventLogWriterOptions = {},
  ) {
    this.maxBytes = options.maxBytes ?? config.EVENT_LOG_MAX_BYTES;
    this.maxPendingBytes = options.maxPendingBytes ?? config.EVENT_LOG_MAX_PENDING_BYTES;
    this.logger = options.logger ?? null;
  }

  setLogger(logger: Logger | null): void {
    this.logger = logger;
  }

  append(kind: string, data: Record<string, unknown>): boolean {
    if (this.closing || this.status === 'closed' || this.status === 'degraded') {
      this.droppedEvents += 1;
      return false;
    }

    const line = `${JSON.stringify({ kind, data })}\n`;
    const bytes = Buffer.byteLength(line);
    if (this.status === 'limited' || this.queuedBytes + bytes > this.maxPendingBytes) {
      this.markLimited(
        this.status === 'limited' ? (this.reason ?? 'event_log_size_limit') : 'pending_queue_limit',
      );
      this.droppedEvents += 1;
      return false;
    }

    this.queue.push(line);
    this.queuedBytes += bytes;
    this.peakQueuedBytes = Math.max(this.peakQueuedBytes, this.queuedBytes);
    this.scheduleDrain();
    return true;
  }

  snapshot(): EventLogSnapshot {
    return {
      status: this.status,
      persisted_bytes: this.persistedBytes,
      queued_bytes: this.queuedBytes,
      peak_queued_bytes: this.peakQueuedBytes,
      dropped_events: this.droppedEvents,
      reason: this.reason,
    };
  }

  async flush(): Promise<void> {
    while (this.queue.length > 0 || this.drainPromise) {
      this.scheduleDrain();
      const current = this.drainPromise;
      if (current) await current;
    }
    if (this.file && this.status !== 'degraded') {
      try {
        await this.file.sync();
      } catch (error) {
        this.markDegraded(error, 'sync');
      }
    }
  }

  close(): Promise<void> {
    if (this.closePromise) return this.closePromise;
    this.closing = true;
    this.closePromise = (async () => {
      await this.flush();
      if (this.file) {
        try {
          await this.file.close();
        } catch (error) {
          this.markDegraded(error, 'close');
        } finally {
          this.file = null;
        }
      }
      if (this.status === 'healthy') this.status = 'closed';
    })();
    return this.closePromise;
  }

  private scheduleDrain(): void {
    if (this.drainPromise || this.queue.length === 0 || this.status === 'degraded') return;
    this.drainPromise = this.drain().finally(() => {
      this.drainPromise = null;
      if (this.queue.length > 0 && this.status !== 'degraded') this.scheduleDrain();
    });
  }

  private async drain(): Promise<void> {
    try {
      if (!this.file) {
        await fs.promises.mkdir(path.dirname(this.filePath), { recursive: true });
        this.file = await fs.promises.open(this.filePath, 'a+');
        this.persistedBytes = (await this.file.stat()).size;
        if (this.persistedBytes >= this.maxBytes) {
          this.markLimited('event_log_size_limit');
        }
      }

      while (this.queue.length > 0 && this.status !== 'degraded') {
        if (this.status === 'limited' && this.reason === 'event_log_size_limit') {
          this.droppedEvents += this.queue.length;
          this.queue = [];
          this.queuedBytes = 0;
          break;
        }
        const batch = this.queue;
        this.queue = [];
        const batchBytes = this.queuedBytes;
        this.queuedBytes = 0;
        const remaining = this.maxBytes - this.persistedBytes;

        if (batchBytes <= remaining) {
          await this.file.writeFile(batch.join(''));
          this.persistedBytes += batchBytes;
          continue;
        }

        const accepted: string[] = [];
        let acceptedBytes = 0;
        for (const line of batch) {
          const lineBytes = Buffer.byteLength(line);
          if (acceptedBytes + lineBytes > remaining) break;
          accepted.push(line);
          acceptedBytes += lineBytes;
        }
        if (accepted.length > 0) {
          await this.file.writeFile(accepted.join(''));
          this.persistedBytes += acceptedBytes;
        }
        this.droppedEvents += batch.length - accepted.length;
        this.markLimited('event_log_size_limit');
      }
    } catch (error) {
      this.queue = [];
      this.queuedBytes = 0;
      this.markDegraded(error, 'write');
    }
  }

  private markLimited(reason: string): void {
    if (this.status !== 'healthy') return;
    this.status = 'limited';
    this.reason = reason;
    this.logger?.warn(
      { runId: this.runId, reason, maxBytes: this.maxBytes, maxPendingBytes: this.maxPendingBytes },
      'experiment event persistence reached a configured limit',
    );
  }

  private markDegraded(error: unknown, operation: string): void {
    this.status = 'degraded';
    this.reason = `filesystem_${operation}_failed`;
    this.logger?.error(
      {
        runId: this.runId,
        operation,
        errorType: error instanceof Error ? error.name : 'UnknownError',
      },
      'experiment event persistence degraded',
    );
  }
}
