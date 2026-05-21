// ============================================================================
// Web Search tool — stub (requires API key configuration)
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const webSearchSchema = toOpenAITool({
  name: 'web_search',
  description: 'Search the web for information',
  parameters: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'The search query',
      },
      allowed_domains: {
        type: 'array',
        items: { type: 'string' },
        description: 'Only include results from these domains',
      },
      blocked_domains: {
        type: 'array',
        items: { type: 'string' },
        description: 'Never include results from these domains',
      },
    },
    required: ['query'],
  },
});

// ---- handler (stub) ----

const webSearchHandler: ToolHandler = (_args, _context) => {
  return JSON.stringify({
    error:
      'Web search requires API key configuration. Set the SEARCH_API_KEY environment variable.',
  });
};

// ---- entry ----

export const webSearchTool: ToolEntry = {
  name: 'web_search',
  toolset: 'web',
  schema: webSearchSchema,
  handler: webSearchHandler,
  requiresEnv: ['SEARCH_API_KEY'],
  emoji: '🌐',
};
