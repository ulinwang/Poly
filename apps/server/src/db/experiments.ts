import { db } from './index';
import type { ExperimentRow } from '../types';

const allowedCols = new Set([
  'id', 'slug', 'n_agents', 'n_ticks', 'persona_set',
  'api_settings_id', 'status', 'started_at', 'finished_at',
  'result_summary', 'created_at',
  'final_yes_mid', 'total_fills', 'total_actions', 'avg_tick_time_ms',
  'checkpoint_path', 'seed', 'api_key_id',
]);

export function saveExperiment(exp: Partial<ExperimentRow>): void {
  if (!exp.id) throw new Error('id is required');
  const clean: Record<string, unknown> = {};
  for (const key of Object.keys(exp)) {
    if (allowedCols.has(key)) clean[key] = (exp as Record<string, unknown>)[key];
  }
  const updateKeys = Object.keys(clean).filter((k) => k !== 'id');

  if (updateKeys.length > 0) {
    const setClause = updateKeys.map((k) => `${k}=@${k}`).join(', ');
    const stmt = db.prepare(`UPDATE experiments SET ${setClause} WHERE id=@id`);
    const result = stmt.run(clean as Record<string, unknown>);
    if (result.changes > 0) return;
  }

  const keys = Object.keys(clean);
  const cols = keys.join(', ');
  const placeholders = keys.map((k) => `@${k}`).join(', ');
  const stmt = db.prepare(`INSERT OR REPLACE INTO experiments (${cols}) VALUES (${placeholders})`);
  stmt.run(clean as Record<string, unknown>);
}

export function getExperiments(limit = 100): ExperimentRow[] {
  return db.prepare('SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?').all(limit) as ExperimentRow[];
}

export function getExperimentsFiltered(
  status?: string | null,
  slug?: string | null,
  limit = 20,
  offset = 0,
): { rows: ExperimentRow[]; total: number } {
  const whereClauses: string[] = [];
  const params: (string | number)[] = [];
  if (status) {
    whereClauses.push('status = ?');
    params.push(status);
  }
  if (slug) {
    whereClauses.push('slug LIKE ?');
    params.push(`%${slug}%`);
  }
  const where = whereClauses.length ? `WHERE ${whereClauses.join(' AND ')}` : '';
  const rows = db
    .prepare(`SELECT * FROM experiments ${where} ORDER BY created_at DESC LIMIT ? OFFSET ?`)
    .all(...params, limit, offset) as ExperimentRow[];
  const totalRow = db.prepare(`SELECT COUNT(*) as cnt FROM experiments ${where}`).get(...params) as { cnt: number };
  return { rows, total: totalRow.cnt };
}

export function searchExperiments(q: string, limit = 20): ExperimentRow[] {
  return db
    .prepare('SELECT * FROM experiments WHERE slug LIKE ? ORDER BY created_at DESC LIMIT ?')
    .all(`%${q}%`, limit) as ExperimentRow[];
}

export function getExperimentStats(): {
  total_runs: number;
  running_count: number;
  avg_agents: number;
  avg_ticks: number;
} {
  const row = db.prepare(`
    SELECT
      COUNT(*) AS total_runs,
      SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count,
      AVG(n_agents) AS avg_agents,
      AVG(n_ticks) AS avg_ticks
    FROM experiments
  `).get() as {
    total_runs: number;
    running_count: number;
    avg_agents: number | null;
    avg_ticks: number | null;
  };
  return {
    total_runs: row.total_runs || 0,
    running_count: row.running_count || 0,
    avg_agents: row.avg_agents ? parseFloat(row.avg_agents.toFixed(2)) : 0,
    avg_ticks: row.avg_ticks ? parseFloat(row.avg_ticks.toFixed(2)) : 0,
  };
}

export function getExperiment(expId: string): ExperimentRow | undefined {
  return db.prepare('SELECT * FROM experiments WHERE id = ?').get(expId) as ExperimentRow | undefined;
}

/**
 * On server startup, any experiment still marked 'running' in the DB is a
 * zombie: the in-memory run state and its Python child died with the previous
 * process. Flag those as 'error' so the UI no longer shows them as live.
 *
 * Paused runs are deliberately left untouched — they have a checkpoint on disk
 * and remain resumable. Returns the number of rows repaired.
 */
export function repairOrphanedRuns(): number {
  const result = db
    .prepare(
      "UPDATE experiments SET status = 'error', finished_at = ? WHERE status = 'running'",
    )
    .run(new Date().toISOString());
  return result.changes;
}
