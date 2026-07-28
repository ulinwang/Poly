import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { pruneRunArtifacts } from './artifact-retention.js';

const tempDirectories: string[] = [];

afterEach(() => {
  for (const directory of tempDirectories.splice(0)) {
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

describe('pruneRunArtifacts', () => {
  it('removes expired logs and checkpoints but preserves recent artifacts', async () => {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'poly-retention-'));
    tempDirectories.push(dataDir);
    const runs = path.join(dataDir, 'runs');
    const checkpoints = path.join(dataDir, 'checkpoints');
    fs.mkdirSync(runs, { recursive: true });
    fs.mkdirSync(checkpoints, { recursive: true });
    const oldLog = path.join(runs, 'old.ndjson');
    const freshLog = path.join(runs, 'fresh.ndjson');
    const oldCheckpoint = path.join(checkpoints, 'old.pkl');
    fs.writeFileSync(oldLog, '{}\n');
    fs.writeFileSync(freshLog, '{}\n');
    fs.writeFileSync(oldCheckpoint, 'checkpoint');
    const now = Date.now();
    const old = new Date(now - 45 * 24 * 60 * 60 * 1_000);
    fs.utimesSync(oldLog, old, old);
    fs.utimesSync(oldCheckpoint, old, old);

    await expect(pruneRunArtifacts(dataDir, now)).resolves.toEqual({
      eventLogsRemoved: 1,
      checkpointsRemoved: 1,
    });
    expect(fs.existsSync(oldLog)).toBe(false);
    expect(fs.existsSync(oldCheckpoint)).toBe(false);
    expect(fs.existsSync(freshLog)).toBe(true);
  });
});

