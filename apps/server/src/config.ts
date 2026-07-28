import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Repo root: apps/server/src/config.ts -> ../../../ -> repo root
const REPO_ROOT = process.env.POLY_ROOT || path.resolve(__dirname, '../../../');

function positiveIntegerEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === '') return fallback;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new Error(`${name} must be a positive integer`);
  }
  return value;
}

export const config = {
  PORT: parseInt(process.env.PORT || '8765', 10),
  HOST: process.env.HOST || '127.0.0.1',
  DATA_DIR: process.env.DATA_DIR || './data',
  NODE_ENV: process.env.NODE_ENV || 'production',
  API_TOKEN: process.env.POLY_API_TOKEN || '',
  API_READ_TOKEN: process.env.POLY_API_READ_TOKEN || '',
  MAX_EXPERIMENT_AGENTS: positiveIntegerEnv('POLY_MAX_EXPERIMENT_AGENTS', 100),
  MAX_EXPERIMENT_TICKS: positiveIntegerEnv('POLY_MAX_EXPERIMENT_TICKS', 200),
  MAX_ACTIVE_RUNS: positiveIntegerEnv('POLY_MAX_ACTIVE_RUNS', 2),
  GAMMA_API_BASE: 'https://gamma-api.polymarket.com',
  // Absolute path to the repo root, used as the cwd when spawning the Python
  // simulation core. Override with POLY_ROOT for non-standard layouts.
  REPO_ROOT,
  // Python interpreter for the sim core (relative to REPO_ROOT or absolute).
  PYTHON_BIN: process.env.POLY_PYTHON || '.venv/bin/python3',
};
