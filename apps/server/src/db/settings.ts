import { db } from './index.js';
import type { ApiSettings } from '../types/index.js';
import { encrypt, decrypt } from './crypto.js';

/** Raw row shape as stored in SQLite. `api_key` holds the encrypted blob. */
interface ApiSettingsRow {
  id: number;
  provider: ApiSettings['provider'];
  model: string;
  api_key: string; // encrypted (base64)
  base_url: string | null;
  temperature: number;
  max_tokens: number;
}

function getLatestRow(): ApiSettingsRow | undefined {
  return db
    .prepare('SELECT * FROM api_settings ORDER BY updated_at DESC, id DESC LIMIT 1')
    .get() as ApiSettingsRow | undefined;
}

/**
 * Public/safe settings view: never includes the plaintext (or encrypted) key.
 * Exposes `api_key_set` so the client can show whether a key is configured.
 */
export function getApiSettings(): ApiSettings | undefined {
  const row = getLatestRow();
  if (!row) return undefined;
  return {
    id: row.id,
    provider: row.provider,
    model: row.model,
    base_url: row.base_url ?? undefined,
    temperature: row.temperature,
    max_tokens: row.max_tokens,
    api_key_set: !!row.api_key,
  };
}

/**
 * Internal view including the decrypted plaintext API key. Use only for
 * outbound LLM calls / spawning the sim subprocess. Never return to the client.
 */
export function getApiSettingsDecrypted(): ApiSettings | undefined {
  const row = getLatestRow();
  if (!row) return undefined;
  let apiKey = '';
  if (row.api_key) {
    try {
      apiKey = decrypt(row.api_key);
    } catch {
      apiKey = '';
    }
  }
  return {
    id: row.id,
    provider: row.provider,
    model: row.model,
    api_key: apiKey,
    base_url: row.base_url ?? undefined,
    temperature: row.temperature,
    max_tokens: row.max_tokens,
    api_key_set: !!row.api_key,
  };
}

/**
 * Persist settings. If `api_key` is a non-empty string it is encrypted and
 * stored; otherwise the previously stored (encrypted) key is preserved.
 */
export function saveApiSettings(settings: Omit<ApiSettings, 'id'> & { id?: number }): number {
  let encryptedKey: string;
  if (settings.api_key && settings.api_key.length > 0) {
    encryptedKey = encrypt(settings.api_key);
  } else {
    // Preserve existing key when caller does not supply a new one.
    const prev = getLatestRow();
    encryptedKey = prev?.api_key ?? '';
  }

  const stmt = db.prepare(`
    INSERT INTO api_settings (provider, model, api_key, base_url, temperature, max_tokens)
    VALUES (@provider, @model, @api_key, @base_url, @temperature, @max_tokens)
  `);
  const info = stmt.run({
    provider: settings.provider,
    model: settings.model,
    api_key: encryptedKey,
    base_url: settings.base_url ?? null,
    temperature: settings.temperature,
    max_tokens: settings.max_tokens,
  });
  return Number(info.lastInsertRowid);
}
