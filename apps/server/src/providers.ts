// Single source of truth for the LLM provider catalog shared by the
// /providers and /settings routes. Agent inference runs through litellm
// (see sim/agent/decision/llm.py):
//   - OpenAI-compatible providers expose a `base_url`; the model id is sent
//     as-is to that endpoint (litellm's openai-compatible handler), which
//     also forwards custom/newest model names the registry may not know yet.
//   - Native-only providers (e.g. Anthropic) omit `base_url` and use a
//     litellm-prefixed model id (e.g. "anthropic/claude-..."), routed by
//     litellm directly.
import type { ProviderInfo } from './types';

export interface ProviderCatalogEntry extends ProviderInfo {
  /** OpenAI-compatible API base; omitted for litellm-native providers. */
  base_url?: string;
}

export const PROVIDER_CATALOG: ProviderCatalogEntry[] = [
  {
    id: 'deepseek',
    name: 'DeepSeek',
    base_url: 'https://api.deepseek.com/v1',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    requires_base_url: false,
  },
  {
    id: 'kimi',
    name: 'Kimi (Moonshot)',
    base_url: 'https://api.moonshot.cn/v1',
    models: ['kimi-k2-0905-preview', 'kimi-latest', 'moonshot-v1-128k', 'moonshot-v1-32k', 'moonshot-v1-8k'],
    requires_base_url: false,
  },
  {
    id: 'openai',
    name: 'OpenAI',
    base_url: 'https://api.openai.com/v1',
    models: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'o3', 'o3-mini', 'o1'],
    requires_base_url: false,
  },
  {
    id: 'xai',
    name: 'xAI (Grok)',
    base_url: 'https://api.x.ai/v1',
    models: ['grok-4', 'grok-3', 'grok-3-mini'],
    requires_base_url: false,
  },
  {
    id: 'gemini',
    name: 'Google Gemini',
    base_url: 'https://generativelanguage.googleapis.com/v1beta/openai',
    models: ['gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.0-flash'],
    requires_base_url: false,
  },
  {
    id: 'mistral',
    name: 'Mistral',
    base_url: 'https://api.mistral.ai/v1',
    models: ['mistral-large-latest', 'mistral-small-latest'],
    requires_base_url: false,
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    // Native-only: litellm routes "anthropic/<model>" directly (no base_url).
    models: ['anthropic/claude-opus-4-8', 'anthropic/claude-sonnet-4-6', 'anthropic/claude-haiku-4-5'],
    requires_base_url: false,
  },
  {
    id: 'custom',
    name: 'Custom (OpenAI-compatible)',
    models: [],
    requires_base_url: true,
  },
];

export function providerBaseUrl(id: string): string | undefined {
  return PROVIDER_CATALOG.find((p) => p.id === id)?.base_url;
}

/** API-facing view (id, name, models, requires_base_url, base_url). */
export function providerInfoList(): ProviderCatalogEntry[] {
  return PROVIDER_CATALOG;
}
