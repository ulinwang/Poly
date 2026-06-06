import type { FastifyInstance } from 'fastify';
import type { ProviderInfo } from '../types';

const PROVIDERS: ProviderInfo[] = [
  {
    id: 'deepseek',
    name: 'DeepSeek',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    requires_base_url: false,
  },
  {
    id: 'kimi',
    name: 'Kimi (Moonshot)',
    models: ['moonshot-v1-8k', 'moonshot-v1-32k', 'moonshot-v1-128k'],
    requires_base_url: false,
  },
  {
    id: 'openai',
    name: 'OpenAI',
    models: [
      'gpt-4o',
      'gpt-4o-mini',
      'gpt-4-turbo',
      'gpt-4',
      'gpt-3.5-turbo',
      'o1-preview',
      'o1-mini',
    ],
    requires_base_url: false,
  },
];

export default async function providersRoutes(app: FastifyInstance) {
  app.get('', async () => {
    return { providers: PROVIDERS };
  });
}
