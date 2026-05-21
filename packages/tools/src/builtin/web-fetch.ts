// ============================================================================
// Web Fetch tool — stub (requires API key configuration)
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const webFetchSchema = toOpenAITool({
  name: 'web_fetch',
  description: 'Fetch content from a URL and extract information',
  parameters: {
    type: 'object',
    properties: {
      url: {
        type: 'string',
        description: 'The URL to fetch content from',
      },
      prompt: {
        type: 'string',
        description: 'Instructions for what information to extract from the page',
      },
    },
    required: ['url', 'prompt'],
  },
});

// ---- handler (stub) ----

const webFetchHandler: ToolHandler = (_args, _context) => {
  return JSON.stringify({
    error:
      'Web fetch requires API key configuration. Set the JARVIS_WEB_API_KEY environment variable.',
  });
};

// ---- entry ----

export const webFetchTool: ToolEntry = {
  name: 'web_fetch',
  toolset: 'web',
  schema: webFetchSchema,
  handler: webFetchHandler,
  requiresEnv: ['JARVIS_WEB_API_KEY'],
  isAsync: true,
  emoji: '📄',
};
