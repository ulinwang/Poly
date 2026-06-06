import { db } from './index';
import { encrypt, decrypt } from './crypto';
import type { ApiKey, ApiKeyDecrypted } from '../types';

/** Raw row shape as stored in SQLite. `api_key` holds the encrypted blob. */
interface ApiKeyRow {
  id: number;
  name: string;
  provider: string;
  api_key: string; // encrypted (base64)
  base_url: string | null;
  model: string | null;
  created_at: string;
}

/**
 * Build a masked preview of a plaintext key, e.g. "sk-…a1b2". Never exposes the
 * full secret; falls back to a fixed mask for very short keys.
 */
function maskKey(plain: string): string {
  if (!plain) return '';
  const last4 = plain.slice(-4);
  const prefix = plain.startsWith('sk-') ? 'sk-' : '';
  return `${prefix}…${last4}`;
}

function rowToSafe(row: ApiKeyRow): ApiKey {
  let masked: string;
  try {
    masked = maskKey(decrypt(row.api_key));
  } catch {
    // Corrupt/undecryptable blob — show a generic mask rather than throwing.
    masked = '…';
  }
  return {
    id: row.id,
    name: row.name,
    provider: row.provider,
    base_url: row.base_url ?? undefined,
    model: row.model ?? undefined,
    created_at: row.created_at,
    key_masked: masked,
  };
}

/**
 * Safe list view: id/name/provider/base_url/model/created_at plus a masked key
 * preview. Never includes the plaintext (or encrypted) key.
 */
export function listApiKeys(): ApiKey[] {
  const rows = db
    .prepare('SELECT * FROM api_keys ORDER BY created_at DESC, id DESC')
    .all() as ApiKeyRow[];
  return rows.map(rowToSafe);
}

/** Create a named API key, encrypting the plaintext at rest. Returns its id. */
export function createApiKey(input: {
  name: string;
  provider: string;
  api_key: string;
  base_url?: string | null;
  model?: string | null;
}): number {
  const stmt = db.prepare(`
    INSERT INTO api_keys (name, provider, api_key, base_url, model)
    VALUES (@name, @provider, @api_key, @base_url, @model)
  `);
  const info = stmt.run({
    name: input.name,
    provider: input.provider,
    api_key: encrypt(input.api_key),
    base_url: input.base_url ?? null,
    model: input.model ?? null,
  });
  return Number(info.lastInsertRowid);
}

/** Delete a named API key by id. Returns true if a row was removed. */
export function deleteApiKey(id: number): boolean {
  const info = db.prepare('DELETE FROM api_keys WHERE id = ?').run(id);
  return info.changes > 0;
}

/**
 * Internal view including the decrypted plaintext key. Use only for outbound
 * LLM calls / spawning the sim subprocess. Never return to the client.
 */
export function getApiKeyDecrypted(id: number): ApiKeyDecrypted | undefined {
  const row = db.prepare('SELECT * FROM api_keys WHERE id = ?').get(id) as
    | ApiKeyRow
    | undefined;
  if (!row) return undefined;
  let apiKey: string;
  try {
    apiKey = decrypt(row.api_key);
  } catch {
    apiKey = '';
  }
  return {
    id: row.id,
    name: row.name,
    provider: row.provider,
    api_key: apiKey,
    base_url: row.base_url ?? undefined,
    model: row.model ?? undefined,
  };
}
