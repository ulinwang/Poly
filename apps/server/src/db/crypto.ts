import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { config } from '../config.js';

const ALGORITHM = 'aes-256-gcm';
const KEY_LENGTH = 32; // 256 bits
const IV_LENGTH = 12; // 96-bit nonce recommended for GCM
const TAG_LENGTH = 16; // 128-bit auth tag

/**
 * Derive the 32-byte master key used for AES-256-GCM.
 *
 * Priority:
 *   1. POLY_SECRET environment variable. Hashed with SHA-256 so any-length
 *      secret yields a valid 32-byte key.
 *   2. Stable fallback: a random 32-byte key persisted in DATA_DIR/.keyfile.
 *      Generated once on first use; reused afterwards. A warning is printed so
 *      operators know to set POLY_SECRET in production.
 */
function resolveMasterKey(): Buffer {
  const secret = process.env.POLY_SECRET;
  if (secret && secret.length > 0) {
    return crypto.createHash('sha256').update(secret, 'utf8').digest();
  }

  const dataDir = path.resolve(config.DATA_DIR);
  const keyfilePath = path.join(dataDir, '.keyfile');

  if (fs.existsSync(keyfilePath)) {
    const existing = fs.readFileSync(keyfilePath);
    if (existing.length === KEY_LENGTH) {
      return existing;
    }
    // Corrupt/short keyfile — regenerate below.
  }

  if (!fs.existsSync(dataDir)) {
    fs.mkdirSync(dataDir, { recursive: true });
  }
  const generated = crypto.randomBytes(KEY_LENGTH);
  fs.writeFileSync(keyfilePath, generated, { mode: 0o600 });
  console.warn(
    `[crypto] POLY_SECRET is not set. Generated a random key at ${keyfilePath}. ` +
      'Set POLY_SECRET in production to ensure stable, externally managed encryption.',
  );
  return generated;
}

// Resolved lazily once, then cached for the process lifetime.
let cachedKey: Buffer | null = null;
function getKey(): Buffer {
  if (!cachedKey) {
    cachedKey = resolveMasterKey();
  }
  return cachedKey;
}

/**
 * Encrypt a UTF-8 string with AES-256-GCM.
 * Returns base64 of: iv (12B) || authTag (16B) || ciphertext.
 */
export function encrypt(plain: string): string {
  const iv = crypto.randomBytes(IV_LENGTH);
  const cipher = crypto.createCipheriv(ALGORITHM, getKey(), iv);
  const ciphertext = Buffer.concat([cipher.update(plain, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, ciphertext]).toString('base64');
}

/**
 * Decrypt a value produced by {@link encrypt}.
 * Returns the original UTF-8 string. Throws if the payload is malformed or the
 * auth tag does not verify.
 */
export function decrypt(enc: string): string {
  const raw = Buffer.from(enc, 'base64');
  if (raw.length < IV_LENGTH + TAG_LENGTH) {
    throw new Error('Invalid ciphertext: too short');
  }
  const iv = raw.subarray(0, IV_LENGTH);
  const tag = raw.subarray(IV_LENGTH, IV_LENGTH + TAG_LENGTH);
  const ciphertext = raw.subarray(IV_LENGTH + TAG_LENGTH);
  const decipher = crypto.createDecipheriv(ALGORITHM, getKey(), iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]).toString('utf8');
}
