// ============================================================================
// Tavily backend — WebSearch + WebFetch via Tavily API
// ============================================================================

import type { WebSearchBackend, WebSearchResult } from './web-search.js';
import type { WebFetchBackend } from './web-fetch.js';

const TAVILY_BASE = 'https://api.tavily.com';

export interface TavilyOptions {
  apiKey?: string;
  baseUrl?: string;
}

// ---- TavilySearchBackend ----

export class TavilySearchBackend implements WebSearchBackend {
  private apiKey: string;
  private baseUrl: string;

  constructor(options: TavilyOptions = {}) {
    this.apiKey = options.apiKey ?? process.env['TAVILY_API_KEY'] ?? '';
    this.baseUrl = options.baseUrl ?? TAVILY_BASE;
  }

  async search(params: {
    query: string;
    maxResults?: number;
    allowedDomains?: string[];
    blockedDomains?: string[];
  }): Promise<{ results: WebSearchResult[] }> {
    if (!this.apiKey) {
      throw new Error('TAVILY_API_KEY not set. Set the environment variable or pass apiKey in options.');
    }

    const body: Record<string, unknown> = {
      api_key: this.apiKey,
      query: params.query,
      max_results: params.maxResults ?? 5,
    };

    if (params.allowedDomains?.length) {
      body['include_domains'] = params.allowedDomains;
    }
    if (params.blockedDomains?.length) {
      body['exclude_domains'] = params.blockedDomains;
    }

    const response = await fetch(`${this.baseUrl}/search`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Tavily Search API returned ${response.status}: ${response.statusText}`);
    }

    const data = (await response.json()) as Record<string, unknown>;
    const rawResults = (data['results'] ?? []) as Array<Record<string, unknown>>;

    return {
      results: rawResults.map((r) => ({
        title: String(r['title'] ?? ''),
        url: String(r['url'] ?? ''),
        snippet: String(r['content'] ?? r['snippet'] ?? ''),
      })),
    };
  }
}

// ---- TavilyFetchBackend ----

export class TavilyFetchBackend implements WebFetchBackend {
  private apiKey: string;
  private baseUrl: string;

  constructor(options: TavilyOptions = {}) {
    this.apiKey = options.apiKey ?? process.env['TAVILY_API_KEY'] ?? '';
    this.baseUrl = options.baseUrl ?? TAVILY_BASE;
  }

  async fetch(url: string, prompt: string): Promise<string> {
    if (!this.apiKey) {
      throw new Error('TAVILY_API_KEY not set. Set the environment variable or pass apiKey in options.');
    }

    const body: Record<string, unknown> = {
      api_key: this.apiKey,
      urls: [url],
      extract_depth: 'basic',
    };

    const response = await fetch(`${this.baseUrl}/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      throw new Error(`Tavily Extract API returned ${response.status}: ${response.statusText}`);
    }

    const data = (await response.json()) as Record<string, unknown>;
    const results = (data['results'] ?? []) as Array<Record<string, unknown>>;
    const firstResult = results[0];

    if (!firstResult) {
      throw new Error(`Tavily Extract returned no results for: ${url}`);
    }

    const rawContent = String(firstResult['raw_content'] ?? firstResult['content'] ?? '');
    if (!rawContent) {
      throw new Error(`Tavily Extract returned empty content for: ${url}`);
    }

    return `Extracted from ${url}\nPrompt: ${prompt}\n\n${rawContent}`;
  }
}

// ---- auto-detect ----

/** Returns a Tavily search backend if TAVILY_API_KEY is set, otherwise null. */
export function tryCreateTavilySearch(): TavilySearchBackend | null {
  const key = process.env['TAVILY_API_KEY'];
  if (!key) return null;
  return new TavilySearchBackend({ apiKey: key });
}

/** Returns a Tavily fetch backend if TAVILY_API_KEY is set, otherwise null. */
export function tryCreateTavilyFetch(): TavilyFetchBackend | null {
  const key = process.env['TAVILY_API_KEY'];
  if (!key) return null;
  return new TavilyFetchBackend({ apiKey: key });
}
