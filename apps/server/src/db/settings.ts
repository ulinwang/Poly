import { db } from './index';
import type { ApiSettings } from '../types';

export function getApiSettings(): ApiSettings | undefined {
  const row = db
    .prepare('SELECT * FROM api_settings ORDER BY updated_at DESC LIMIT 1')
    .get() as ApiSettings | undefined;
  return row;
}

export function saveApiSettings(settings: Omit<ApiSettings, 'id'> & { id?: number }): number {
  const stmt = db.prepare(`
    INSERT INTO api_settings (provider, model, api_key, base_url, temperature, max_tokens)
    VALUES (@provider, @model, @api_key, @base_url, @temperature, @max_tokens)
  `);
  const info = stmt.run(settings as Record<string, unknown>);
  return Number(info.lastInsertRowid);
}
