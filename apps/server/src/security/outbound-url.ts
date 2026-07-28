import { lookup } from 'node:dns/promises';
import { isIP } from 'node:net';
import type { LookupAddress } from 'node:dns';

const PRIVATE_HOST_SUFFIXES = ['.localhost', '.local', '.internal', '.home.arpa'];

function stripIpv6Brackets(hostname: string): string {
  return hostname.startsWith('[') && hostname.endsWith(']')
    ? hostname.slice(1, -1)
    : hostname;
}

function isPublicIpv4(address: string): boolean {
  const octets = address.split('.').map(Number);
  if (
    octets.length !== 4 ||
    octets.some((octet) => !Number.isInteger(octet) || octet < 0 || octet > 255)
  ) {
    return false;
  }

  const [a, b, c] = octets;
  return !(
    a === 0 ||
    a === 10 ||
    a === 127 ||
    a >= 224 ||
    (a === 100 && b >= 64 && b <= 127) ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 0 && c === 0) ||
    (a === 192 && b === 0 && c === 2) ||
    (a === 192 && b === 168) ||
    (a === 198 && (b === 18 || b === 19)) ||
    (a === 198 && b === 51 && c === 100) ||
    (a === 203 && b === 0 && c === 113)
  );
}

function isPublicIpv6(address: string): boolean {
  const normalized = address.toLowerCase();
  if (normalized.includes('%')) return false;

  return !(
    normalized === '::' ||
    normalized === '::1' ||
    normalized.startsWith('::ffff:') ||
    normalized.startsWith('64:ff9b:') ||
    normalized.startsWith('fc') ||
    normalized.startsWith('fd') ||
    /^fe[89ab]/.test(normalized) ||
    /^fe[c-f]/.test(normalized) ||
    normalized.startsWith('ff') ||
    normalized.startsWith('2001:db8:')
  );
}

function isPublicIp(address: string): boolean {
  const family = isIP(address);
  if (family === 4) return isPublicIpv4(address);
  if (family === 6) return isPublicIpv6(address);
  return false;
}

function configuredOrigins(rawAllowlist: string | undefined): Set<string> {
  const origins = new Set<string>();
  for (const value of (rawAllowlist ?? '').split(',')) {
    const candidate = value.trim();
    if (!candidate) continue;
    try {
      const url = new URL(candidate);
      if (
        (url.protocol === 'http:' || url.protocol === 'https:') &&
        !url.username &&
        !url.password &&
        url.pathname === '/' &&
        !url.search &&
        !url.hash
      ) {
        origins.add(url.origin);
      }
    } catch {
      // Ignore malformed allowlist entries instead of weakening the policy.
    }
  }
  return origins;
}

export function normalizeLlmBaseUrl(value: string): string {
  const url = new URL(value.trim());
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Endpoint must use HTTP or HTTPS');
  }
  if (url.username || url.password) {
    throw new Error('Endpoint URL must not include credentials');
  }
  if (url.search || url.hash) {
    throw new Error('Endpoint URL must not include a query or fragment');
  }
  url.pathname = url.pathname.replace(/\/+$/, '') || '/';
  return url.toString().replace(/\/$/, '');
}

export async function validateOutboundLlmUrl(
  value: string,
  rawAllowlist = process.env.POLY_LLM_ENDPOINT_ALLOWLIST,
): Promise<string> {
  const normalized = normalizeLlmBaseUrl(value);
  const url = new URL(normalized);
  const allowlisted = configuredOrigins(rawAllowlist).has(url.origin);

  if (url.protocol !== 'https:' && !allowlisted) {
    throw new Error('Endpoint must use HTTPS unless its origin is explicitly allowlisted');
  }
  if (allowlisted) return normalized;

  const hostname = stripIpv6Brackets(url.hostname).toLowerCase().replace(/\.$/, '');
  if (
    hostname === 'localhost' ||
    !hostname.includes('.') ||
    PRIVATE_HOST_SUFFIXES.some((suffix) => hostname.endsWith(suffix))
  ) {
    throw new Error('Endpoint host is not publicly routable');
  }

  const literalFamily = isIP(hostname);
  if (literalFamily !== 0) {
    if (!isPublicIp(hostname)) {
      throw new Error('Endpoint host is not publicly routable');
    }
    return normalized;
  }

  let addresses: LookupAddress[];
  try {
    addresses = await lookup(hostname, { all: true, verbatim: true });
  } catch {
    throw new Error('Endpoint host could not be resolved');
  }
  if (addresses.length === 0 || addresses.some(({ address }) => !isPublicIp(address))) {
    throw new Error('Endpoint host is not publicly routable');
  }

  return normalized;
}
