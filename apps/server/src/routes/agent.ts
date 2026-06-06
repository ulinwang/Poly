import type { FastifyInstance } from 'fastify';
import { spawn } from 'child_process';
import { config } from '../config';

interface AgentInfo {
  tools: unknown[];
  prompt_templates: Record<string, unknown>;
}

const CACHE_TTL_MS = 30_000;
let cache: { value: AgentInfo; at: number } | null = null;

/**
 * Spawn `PYTHON_BIN sim/agent/introspect.py` (cwd = REPO_ROOT), collect its
 * stdout, and parse the JSON payload. Rejects on spawn error, non-zero exit,
 * or malformed JSON so the route can return a clean error.
 */
function runIntrospect(): Promise<AgentInfo> {
  return new Promise((resolve, reject) => {
    const child = spawn(config.PYTHON_BIN, ['sim/agent/introspect.py'], {
      cwd: config.REPO_ROOT,
    });

    let stdout = '';
    let stderr = '';
    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk: string) => { stdout += chunk; });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk: string) => { stderr += chunk; });

    child.on('error', (err) => {
      reject(new Error(`failed to spawn python: ${err.message}`));
    });

    child.on('exit', (code) => {
      if (code !== 0) {
        reject(new Error(`introspect.py exited with code ${code}: ${stderr.trim()}`));
        return;
      }
      try {
        const parsed = JSON.parse(stdout) as AgentInfo;
        resolve({
          tools: Array.isArray(parsed.tools) ? parsed.tools : [],
          prompt_templates: parsed.prompt_templates ?? {},
        });
      } catch (e) {
        reject(new Error(`failed to parse introspect.py output: ${(e as Error).message}`));
      }
    });
  });
}

export default async function agentRoutes(app: FastifyInstance) {
  // GET /api/v1/agent/info — tool schemas + prompt templates from the Python
  // introspection script. Cached for 30s; failures degrade gracefully to a
  // 500 with a message rather than crashing.
  app.get('/info', async (_req, reply) => {
    if (cache && Date.now() - cache.at < CACHE_TTL_MS) {
      return cache.value;
    }
    try {
      const value = await runIntrospect();
      cache = { value, at: Date.now() };
      return value;
    } catch (err) {
      reply.status(500);
      return { message: (err as Error).message, tools: [], prompt_templates: {} };
    }
  });
}
