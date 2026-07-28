import fs from 'node:fs';
import path from 'node:path';
import { config } from '../config.js';

interface RetentionResult {
  eventLogsRemoved: number;
  checkpointsRemoved: number;
}

async function pruneDirectory(directory: string, suffix: string, cutoffMs: number): Promise<number> {
  let entries: fs.Dirent[];
  try {
    entries = await fs.promises.readdir(directory, { withFileTypes: true });
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === 'ENOENT') return 0;
    throw error;
  }

  let removed = 0;
  await Promise.all(
    entries.map(async (entry) => {
      if (!entry.isFile() || !entry.name.endsWith(suffix)) return;
      const filePath = path.join(directory, entry.name);
      const stat = await fs.promises.stat(filePath);
      if (stat.mtimeMs >= cutoffMs) return;
      await fs.promises.unlink(filePath);
      removed += 1;
    }),
  );
  return removed;
}

export async function pruneRunArtifacts(
  dataDir = config.DATA_DIR,
  nowMs = Date.now(),
): Promise<RetentionResult> {
  const dayMs = 24 * 60 * 60 * 1_000;
  const [eventLogsRemoved, checkpointsRemoved] = await Promise.all([
    pruneDirectory(
      path.join(dataDir, 'runs'),
      '.ndjson',
      nowMs - config.EVENT_LOG_RETENTION_DAYS * dayMs,
    ),
    pruneDirectory(
      path.join(dataDir, 'checkpoints'),
      '.pkl',
      nowMs - config.CHECKPOINT_RETENTION_DAYS * dayMs,
    ),
  ]);
  return { eventLogsRemoved, checkpointsRemoved };
}
