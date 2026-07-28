import crypto from 'node:crypto';
import type { FastifyInstance, FastifyRequest } from 'fastify';

export type AuthRole = 'operator' | 'reader';

declare module 'fastify' {
  interface FastifyRequest {
    authRole: AuthRole | null;
  }
}

export interface AuthenticationOptions {
  required: boolean;
  operatorToken?: string;
  readerToken?: string;
}

const PUBLIC_READ_PREFIXES = ['/api/v1/markets', '/api/v1/events'];
const PUBLIC_READ_PATHS = [
  '/api/v1/providers',
  '/api/v1/auth/config',
  '/api/v1/health/live',
  '/api/v1/health/ready',
];

function isPublicRequest(req: FastifyRequest): boolean {
  if (req.method === 'OPTIONS') return true;
  if (req.method !== 'GET' && req.method !== 'HEAD') return false;

  const pathname = req.url.split('?', 1)[0];
  return (
    PUBLIC_READ_PATHS.includes(pathname) ||
    PUBLIC_READ_PREFIXES.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
    )
  );
}

function secureTokenEqual(candidate: string, expected: string | undefined): boolean {
  if (!expected) return false;
  const candidateDigest = crypto.createHash('sha256').update(candidate).digest();
  const expectedDigest = crypto.createHash('sha256').update(expected).digest();
  return crypto.timingSafeEqual(candidateDigest, expectedDigest);
}

function bearerToken(authorization: string | undefined): string | null {
  if (!authorization) return null;
  const match = /^Bearer ([^\s]+)$/.exec(authorization);
  return match?.[1] ?? null;
}

function authenticate(
  authorization: string | undefined,
  options: AuthenticationOptions,
): AuthRole | null {
  const token = bearerToken(authorization);
  if (!token) return null;
  if (secureTokenEqual(token, options.operatorToken)) return 'operator';
  if (secureTokenEqual(token, options.readerToken)) return 'reader';
  return null;
}

export async function installAuthentication(
  app: FastifyInstance,
  options: AuthenticationOptions,
): Promise<void> {
  const operatorToken = options.operatorToken?.trim();
  const readerToken = options.readerToken?.trim();
  const policy: AuthenticationOptions = {
    required: options.required,
    operatorToken,
    readerToken,
  };

  if (policy.required && (!operatorToken || operatorToken.length < 32)) {
    throw new Error(
      'POLY_API_TOKEN must be set to a secret of at least 32 characters when authentication is required',
    );
  }
  if (readerToken && readerToken.length < 32) {
    throw new Error('POLY_API_READ_TOKEN must be at least 32 characters when set');
  }

  app.decorateRequest('authRole', null);
  app.addHook('onRequest', async (req, reply) => {
    if (!policy.required) {
      req.authRole = 'operator';
      return;
    }

    const role = authenticate(req.headers.authorization, policy);
    if (role) {
      req.authRole = role;
    }
    if (isPublicRequest(req)) return;

    if (!role) {
      reply.header('WWW-Authenticate', 'Bearer realm="Poly"');
      return reply.status(401).send({ message: 'Authentication required' });
    }
    if (role === 'reader' && req.method !== 'GET' && req.method !== 'HEAD') {
      return reply.status(403).send({ message: 'Operator permission required' });
    }
  });

  app.get('/api/v1/auth/config', async () => ({
    required: policy.required,
    mode: policy.required ? 'bearer' : 'disabled',
  }));

  app.get('/api/v1/auth/verify', async (req) => ({
    authenticated: true,
    role: req.authRole ?? 'operator',
  }));
}
