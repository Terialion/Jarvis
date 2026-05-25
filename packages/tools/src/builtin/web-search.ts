// ============================================================================
// Web Search tool — factory pattern for pluggable search backends
// Built-in default uses native fetch with a configurable search endpoint
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const webSearchSchema = toOpenAITool({
  name: 'web_search',
  description:
    'Search the web for current information on any topic. Use for news, facts, or data beyond your knowledge cutoff. Returns snippets and source URLs.',
  parameters: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Search query',
      },
      max_results: {
        type: 'number',
        default: 5,
        description: 'Maximum number of search results to return',
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

// ---- backend interface ----

export interface WebSearchResult {
  title: string;
  url: string;
  snippet: string;
}

export interface WebSearchBackend {
  search(params: {
    query: string;
    maxResults?: number;
    allowedDomains?: string[];
    blockedDomains?: string[];
  }): Promise<{ results: WebSearchResult[] }>;
}

// ---- factory ----

export function createWebSearchHandler(backend: WebSearchBackend): ToolHandler {
  return async (args: Record<string, unknown>, _context): Promise<string> => {
    const query = String(args.query ?? '').trim();
    if (!query) {
      return JSON.stringify({ error: 'Missing required parameter: query' });
    }

    const maxResults = Math.max(1, Math.min(20, Number(args.max_results ?? 5)));
    const allowedDomains = Array.isArray(args.allowed_domains)
      ? args.allowed_domains.map(String)
      : undefined;
    const blockedDomains = Array.isArray(args.blocked_domains)
      ? args.blocked_domains.map(String)
      : undefined;

    try {
      const { results } = await backend.search({
        query,
        maxResults,
        allowedDomains,
        blockedDomains,
      });

      return JSON.stringify({
        query,
        results: results.map((r) => ({
          title: r.title,
          url: r.url,
          snippet: r.snippet,
        })),
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `Web search failed: ${message}` });
    }
  };
}

export function createWebSearchTool(backend: WebSearchBackend): ToolEntry {
  return {
    name: 'web_search',
    toolset: 'web',
    schema: webSearchSchema,
    handler: createWebSearchHandler(backend),
    isAsync: true,
    emoji: '🌐',
    maxResultSizeChars: 50_000,
  };
}

// ---- built-in default backend (uses a configurable search endpoint) ----

export class DefaultWebSearchBackend implements WebSearchBackend {
  private endpoint: string;
  private apiKey: string;

  constructor(endpoint?: string, apiKey?: string) {
    this.endpoint = endpoint ?? process.env['SEARCH_API_URL'] ?? '';
    this.apiKey = apiKey ?? process.env['SEARCH_API_KEY'] ?? '';
  }

  async search(params: {
    query: string;
    maxResults?: number;
    allowedDomains?: string[];
    blockedDomains?: string[];
  }): Promise<{ results: WebSearchResult[] }> {
    if (!this.endpoint || !this.apiKey) {
      throw new Error(
        'Web search not configured. Set SEARCH_API_URL and SEARCH_API_KEY, or provide a custom backend.',
      );
    }

    const response = await fetch(this.endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        query: params.query,
        max_results: params.maxResults ?? 5,
        include_domains: params.allowedDomains ?? [],
        exclude_domains: params.blockedDomains ?? [],
      }),
    });

    if (!response.ok) {
      throw new Error(`Search API returned ${response.status}: ${response.statusText}`);
    }

    const data = (await response.json()) as Record<string, unknown>;
    const rawResults = (data['results'] ?? data['data'] ?? []) as Array<Record<string, unknown>>;

    return {
      results: rawResults.map((r) => ({
        title: String(r['title'] ?? ''),
        url: String(r['url'] ?? ''),
        snippet: String(r['snippet'] ?? r['content'] ?? r['description'] ?? ''),
      })),
    };
  }
}

// ---- static tool entry (compat: kept for allBuiltinTools) ----
// This version uses env vars and falls back to an error message.
const webSearchHandler: ToolHandler = async (args, _context) => {
  const endpoint = process.env['SEARCH_API_URL'];
  const apiKey = process.env['SEARCH_API_KEY'];

  if (!endpoint || !apiKey) {
    return JSON.stringify({
      error:
        'Web search requires API key configuration. Set SEARCH_API_URL and SEARCH_API_KEY environment variables, or wire a custom backend via createWebSearchTool().',
    });
  }

  const backend = new DefaultWebSearchBackend(endpoint, apiKey);
  return createWebSearchHandler(backend)(args, _context);
};

export const webSearchTool: ToolEntry = {
  name: 'web_search',
  toolset: 'web',
  schema: webSearchSchema,
  handler: webSearchHandler,
  requiresEnv: ['SEARCH_API_KEY'],
  isAsync: true,
  emoji: '🌐',
  maxResultSizeChars: 50_000,
};
