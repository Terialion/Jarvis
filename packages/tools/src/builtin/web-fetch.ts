// ============================================================================
// Web Fetch tool — fetch content from a URL with an extraction prompt
// Uses native fetch() with configurable backend
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const webFetchSchema = toOpenAITool({
  name: 'web_fetch',
  description:
    'Fetch content from a specified URL and processes it. Fetches the URL content, converts HTML to text, and returns the content. Uses a self-cleaning 15-minute cache. For authenticated URLs (Google Docs, Confluence, Jira, GitHub), prefer specialized MCP tools.',
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

// ---- helpers ----

function stripHtml(html: string): string {
  return html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#x27;/g, "'")
    .replace(/&#(\d+);/g, (_, d) => String.fromCharCode(Number(d)))
    .replace(/\s+/g, ' ')
    .trim();
}

// Simple in-memory cache with 15-minute TTL
const fetchCache = new Map<string, { content: string; timestamp: number }>();
const CACHE_TTL_MS = 15 * 60 * 1000; // 15 minutes

// ---- factory ----

export interface WebFetchBackend {
  fetch(url: string, prompt: string): Promise<string>;
}

export function createWebFetchHandler(backend?: WebFetchBackend): ToolHandler {
  return async (args: Record<string, unknown>, _context): Promise<string> => {
    const url = String(args.url ?? '').trim();
    const prompt = String(args.prompt ?? '').trim();

    if (!url) {
      return JSON.stringify({ error: 'Missing required parameter: url' });
    }
    if (!prompt) {
      return JSON.stringify({ error: 'Missing required parameter: prompt' });
    }

    // Validate URL
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(url);
    } catch {
      return JSON.stringify({ error: `Invalid URL: ${url}` });
    }

    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      return JSON.stringify({ error: `Unsupported protocol: ${parsedUrl.protocol}. Only http: and https: are allowed.` });
    }

    // Check cache
    const cacheKey = `${url}::${prompt.slice(0, 100)}`;
    const cached = fetchCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return JSON.stringify({
        url,
        prompt,
        content: cached.content,
        cached: true,
      });
    }

    // If a custom backend is provided, use it
    if (backend) {
      try {
        const content = await backend.fetch(url, prompt);
        fetchCache.set(cacheKey, { content, timestamp: Date.now() });
        return JSON.stringify({ url, prompt, content, cached: false });
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err);
        return JSON.stringify({ error: `Web fetch failed: ${message}` });
      }
    }

    // Default: native fetch with HTML stripping
    try {
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Jarvis/0.1 (web-fetch)',
          Accept: 'text/html, text/plain, */*',
        },
        signal: AbortSignal.timeout(30_000),
      });

      if (!response.ok) {
        return JSON.stringify({
          error: `HTTP ${response.status}: ${response.statusText}`,
          url,
        });
      }

      const contentType = response.headers.get('content-type') ?? '';
      const raw = await response.text();

      let content: string;
      if (contentType.includes('text/html')) {
        content = stripHtml(raw);
      } else {
        content = raw;
      }

      // Truncate to reasonable size
      if (content.length > 50_000) {
        content = content.slice(0, 50_000) + '\n\n... [truncated]';
      }

      fetchCache.set(cacheKey, { content, timestamp: Date.now() });

      return JSON.stringify({
        url,
        prompt,
        content,
        contentType,
        contentLength: raw.length,
        cached: false,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      return JSON.stringify({ error: `Web fetch failed: ${message}`, url });
    }
  };
}

// ---- static tool entry (for allBuiltinTools) ----

const webFetchHandler: ToolHandler = createWebFetchHandler();

export const webFetchTool: ToolEntry = {
  name: 'web_fetch',
  toolset: 'web',
  schema: webFetchSchema,
  handler: webFetchHandler,
  isAsync: true,
  emoji: '📄',
  maxResultSizeChars: 50_000,
};
