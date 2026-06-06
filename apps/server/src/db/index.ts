import Database from 'better-sqlite3';
import path from 'path';
import fs from 'fs';
import { config } from '../config';

const dbDir = path.resolve(config.DATA_DIR);
if (!fs.existsSync(dbDir)) {
  fs.mkdirSync(dbDir, { recursive: true });
}

const dbPath = path.join(dbDir, 'webapp.db');
const db = new Database(dbPath);
db.pragma('journal_mode = WAL');

const initSQL = `
CREATE TABLE IF NOT EXISTS api_settings (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key TEXT NOT NULL,
    base_url TEXT,
    temperature REAL DEFAULT 0.7,
    max_tokens INTEGER DEFAULT 2048,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiments (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL,
    n_agents INTEGER NOT NULL,
    n_ticks INTEGER NOT NULL,
    persona_set TEXT NOT NULL,
    api_settings_id INTEGER REFERENCES api_settings(id),
    status TEXT NOT NULL,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    result_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    final_yes_mid REAL,
    total_fills INTEGER,
    total_actions INTEGER,
    avg_tick_time_ms REAL
);

CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
CREATE INDEX IF NOT EXISTS idx_experiments_slug ON experiments(slug);
`;

db.exec(initSQL);

// Gracefully add result columns if they don't exist yet
const expectedCols = [
  ['final_yes_mid', 'REAL'],
  ['total_fills', 'INTEGER'],
  ['total_actions', 'INTEGER'],
  ['avg_tick_time_ms', 'REAL'],
  // Path to the pickle checkpoint written when a run is paused; used by
  // POST /:id/resume to continue the simulation. NULL unless paused.
  ['checkpoint_path', 'TEXT'],
  // RNG seed used for the run (reproducibility). NULL for legacy rows.
  ['seed', 'INTEGER'],
];
const existingCols = db
  .prepare("PRAGMA table_info(experiments)")
  .all() as Array<{ name: string }>;
const colNames = new Set(existingCols.map((c) => c.name));
for (const [col, typ] of expectedCols) {
  if (!colNames.has(col)) {
    db.exec(`ALTER TABLE experiments ADD COLUMN ${col} ${typ}`);
  }
}

export { db };
