import type { FastifyInstance } from 'fastify';
import { listApiKeys, createApiKey, deleteApiKey } from '../db/apikeys.js';
import { providerBaseUrl } from '../providers.js';

interface CreateKeyBody {
  name?: string;
  provider?: string;
  api_key?: string;
  base_url?: string;
  model?: string;
}

export default async function keysRoutes(app: FastifyInstance) {
  // List stored keys (safe view: masked key only, never plaintext).
  app.get('', async () => {
    return { keys: listApiKeys() };
  });

  // Create a new named key. The plaintext is encrypted at rest and never
  // echoed back; the response is the refreshed safe list.
  app.post('', async (req, reply) => {
    const body = (req.body ?? {}) as CreateKeyBody;
    const name = (body.name ?? '').trim();
    const provider = (body.provider ?? '').trim();
    const apiKey = body.api_key ?? '';
    if (!name) {
      reply.status(400);
      return { message: 'name is required' };
    }
    if (!provider) {
      reply.status(400);
      return { message: 'provider is required' };
    }
    if (!apiKey) {
      reply.status(400);
      return { message: 'api_key is required' };
    }
    // Default the base URL from the provider catalog when the caller omits it,
    // so OpenAI-compatible providers work without re-typing the endpoint.
    const baseUrl = body.base_url?.trim() || providerBaseUrl(provider) || null;
    const id = createApiKey({
      name,
      provider,
      api_key: apiKey,
      base_url: baseUrl,
      model: body.model?.trim() || null,
    });
    reply.status(201);
    return { id, keys: listApiKeys() };
  });

  // Delete a stored key by id.
  app.delete('/:id', async (req, reply) => {
    const { id } = req.params as { id: string };
    const numId = parseInt(id, 10);
    if (!Number.isFinite(numId)) {
      reply.status(400);
      return { message: 'invalid id' };
    }
    const removed = deleteApiKey(numId);
    if (!removed) {
      reply.status(404);
      return { message: 'key not found' };
    }
    return { deleted: true, keys: listApiKeys() };
  });
}
