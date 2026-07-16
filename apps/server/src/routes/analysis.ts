import type { FastifyInstance } from 'fastify';
import { spawn } from 'child_process';
import { config } from '../config.js';

interface AnalysisResult {
  available: boolean;
  message?: string;
  [key: string]: unknown;
}

const CACHE_TTL_MS = 30_000;
const cache = new Map<string, { value: AnalysisResult; at: number }>();

/**
 * Spawn `PYTHON_BIN research/analysis_cli.py <slug>` (cwd = REPO_ROOT) and
 * parse its JSON stdout. The Python side never throws — it returns
 * `{available:false, message}` when ClickHouse is down or the market has no
 * ingested data — so a non-zero exit or unparseable output here is treated as
 * a graceful "unavailable" rather than a hard error.
 */
function runAnalysis(slug: string): Promise<AnalysisResult> {
  return new Promise((resolve) => {
    const child = spawn(config.PYTHON_BIN, ['research/analysis_cli.py', slug], {
      cwd: config.REPO_ROOT,
    });

    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => { stdout += chunk; });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk: string) => { stderr += chunk; });

    child.on('error', (err) => {
      resolve({ available: false, message: `failed to spawn python: ${err.message}` });
    });

    child.on('exit', (code) => {
      try {
        const parsed = JSON.parse(stdout) as AnalysisResult;
        resolve(parsed);
      } catch {
        resolve({
          available: false,
          message:
            code === 0
              ? 'analysis returned no parseable output'
              : `analysis exited with code ${code}: ${stderr.trim() || 'no output'}`,
        });
      }
    });
  });
}

export default async function analysisRoutes(app: FastifyInstance) {
  // GET /api/v1/analysis/:slug — on-chain analytics for a market. Always 200:
  // when no data is ingested the body is { available:false, message }.
  app.get('/:slug', async (req) => {
    const { slug } = req.params as { slug: string };
    const cached = cache.get(slug);
    if (cached && Date.now() - cached.at < CACHE_TTL_MS) {
      return cached.value;
    }
    const value = await runAnalysis(slug);
    cache.set(slug, { value, at: Date.now() });
    return value;
  });
}
