// ============================================================================
// Web Fetch tool — fetch content from a URL with content extraction
// Uses @mozilla/readability for HTML → markdown conversion
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

// ---- schema ----

export const webFetchSchema = toOpenAITool({
  name: 'web_fetch',
  description:
    'Fetch content from a URL and extract readable text. Converts HTML to clean markdown using Readability (Firefox reader mode). Returns structured content with the prompt answered from the page. For GitHub repos, fetches README directly. For authenticated URLs, prefer specialized MCP tools.',
  parameters: {
    type: 'object',
    properties: {
      url: {
        type: 'string',
        description: 'The URL to fetch content from',
      },
      prompt: {
        type: 'string',
        description: 'Question to answer from the fetched content',
      },
    },
    required: ['url', 'prompt'],
  },
});

// ---- HTML → Markdown via Readability ----

let readabilityDeps: {
  Readability: typeof import('@mozilla/readability').Readability;
  parseHTML: typeof import('linkedom').parseHTML;
} | null = null;

async function loadReadability() {
  if (!readabilityDeps) {
    const [readability, linkedom] = await Promise.all([
      import('@mozilla/readability'),
      import('linkedom'),
    ]);
    readabilityDeps = {
      Readability: readability.Readability,
      parseHTML: linkedom.parseHTML,
    };
  }
  return readabilityDeps;
}

/** Extract readable content from HTML using @mozilla/readability */
async function extractReadableContent(
  html: string,
  url: string,
): Promise<{ title: string; text: string } | null> {
  try {
    const { Readability, parseHTML } = await loadReadability();
    // Skip huge HTML to avoid DOM parsing overhead
    if (html.length > 1_000_000) {
      html = html.slice(0, 1_000_000);
    }
    const { document } = parseHTML(html);
    const reader = new Readability(document);
    const article = reader.parse();
    if (!article?.textContent) return null;
    return {
      title: article.title ?? '',
      text: article.textContent.trim(),
    };
  } catch {
    return null;
  }
}

/** Fallback: basic HTML → markdown with tag stripping */
function basicHtmlToMarkdown(html: string): { title: string; text: string } {
  const titleMatch = html.match(/<title[^>]*>([\s\S]*?)<\/title>/i);
  const title = titleMatch ? titleMatch[1].replace(/<[^>]+>/g, '').trim() : '';

  let text = html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<noscript[\s\S]*?<\/noscript>/gi, '');

  // Links → markdown
  text = text.replace(/<a\s+[^>]*href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi, (_, href, body) => {
    const label = body.replace(/<[^>]+>/g, '').trim();
    return label ? `[${label}](${href})` : href;
  });
  // Headers → markdown
  text = text.replace(/<h([1-6])[^>]*>([\s\S]*?)<\/h1>/gi, (_, level, body) => {
    const prefix = '#'.repeat(Math.min(6, Number(level)));
    return `\n${prefix} ${body.replace(/<[^>]+>/g, '').trim()}\n`;
  });
  // List items
  text = text.replace(/<li[^>]*>([\s\S]*?)<\/li>/gi, (_, body) => {
    const label = body.replace(/<[^>]+>/g, '').trim();
    return label ? `\n- ${label}` : '';
  });
  // Block elements → newlines
  text = text
    .replace(/<(br|hr)\s*\/?>/gi, '\n')
    .replace(/<\/(p|div|section|article|header|footer|table|tr|ul|ol)>/gi, '\n');
  // Strip remaining tags
  text = text.replace(/<[^>]+>/g, '');
  // Decode entities
  text = text
    .replace(/&nbsp;/gi, ' ')
    .replace(/&amp;/gi, '&')
    .replace(/&lt;/gi, '<')
    .replace(/&gt;/gi, '>')
    .replace(/&quot;/gi, '"')
    .replace(/&#x27;/gi, "'")
    .replace(/&#(\d+);/gi, (_, d) => String.fromCharCode(Number(d)));
  // Normalize whitespace
  text = text
    .replace(/\r/g, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();

  return { title, text };
}

// ---- SSRF protection ----

function isPrivateIP(hostname: string): boolean {
  // IPv4 private ranges
  if (/^(127\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|0\.)/.test(hostname)) return true;
  // IPv6 loopback
  if (hostname === '::1' || hostname === 'localhost') return true;
  // Link-local
  if (/^(fe80:|fe[89ab]:)/i.test(hostname)) return true;
  return false;
}

// ---- Cache ----

interface CacheEntry {
  content: string;
  title: string;
  extractor: string;
  timestamp: number;
}

const fetchCache = new Map<string, CacheEntry>();
const CACHE_TTL_MS = 15 * 60 * 1000;
const MAX_CONTENT_CHARS = 50_000;
const MAX_RESPONSE_BYTES = 2_000_000;

// ---- GitHub helpers ----

async function fetchGitHubReadme(owner: string, repo: string): Promise<{ title: string; text: string } | null> {
  const url = `https://raw.githubusercontent.com/${owner}/${repo}/HEAD/README.md`;
  try {
    const resp = await fetch(url, {
      headers: { 'User-Agent': 'Jarvis/0.1 (web-fetch)' },
      signal: AbortSignal.timeout(15_000),
    });
    if (!resp.ok) return null;
    let text = await resp.text();
    if (text.length > MAX_CONTENT_CHARS) text = text.slice(0, MAX_CONTENT_CHARS) + '\n\n... [truncated]';
    return { title: `${owner}/${repo} README`, text };
  } catch {
    return null;
  }
}

// ---- backend interface ----

export interface WebFetchBackend {
  fetch(url: string, prompt: string): Promise<string>;
}

// ---- main handler ----

export function createWebFetchHandler(backend?: WebFetchBackend): ToolHandler {
  return async (args: Record<string, unknown>, _context): Promise<string> => {
    const url = String(args.url ?? '').trim();
    const prompt = String(args.prompt ?? '').trim();

    if (!url) return JSON.stringify({ error: 'Missing required parameter: url' });
    if (!prompt) return JSON.stringify({ error: 'Missing required parameter: prompt' });

    // Validate URL
    let parsedUrl: URL;
    try {
      parsedUrl = new URL(url);
    } catch {
      return JSON.stringify({ error: `Invalid URL: ${url}` });
    }

    if (!['http:', 'https:'].includes(parsedUrl.protocol)) {
      return JSON.stringify({ error: `Unsupported protocol: ${parsedUrl.protocol}` });
    }

    // SSRF: block private IPs
    if (isPrivateIP(parsedUrl.hostname)) {
      return JSON.stringify({ error: `Blocked: ${parsedUrl.hostname} is a private/local address` });
    }

    // Cache check
    const cacheKey = `${url}::${prompt.slice(0, 100)}`;
    const cached = fetchCache.get(cacheKey);
    if (cached && Date.now() - cached.timestamp < CACHE_TTL_MS) {
      return JSON.stringify({
        url, prompt,
        title: cached.title,
        content: cached.content,
        extractor: cached.extractor,
        cached: true,
      });
    }

    // Custom backend
    if (backend) {
      try {
        const content = await backend.fetch(url, prompt);
        fetchCache.set(cacheKey, { content, title: '', extractor: 'backend', timestamp: Date.now() });
        return JSON.stringify({ url, prompt, content, cached: false });
      } catch (err) {
        return JSON.stringify({ error: `Web fetch failed: ${err instanceof Error ? err.message : String(err)}` });
      }
    }

    // Default pipeline
    const start = Date.now();
    try {
      // GitHub repo: fast path via raw README
      const ghMatch = parsedUrl.pathname.match(/^\/([^/]+)\/([^/]+)\/?$/);
      if (parsedUrl.hostname === 'github.com' && ghMatch) {
        const [, owner, repo] = ghMatch;
        const readme = await fetchGitHubReadme(owner, repo);
        if (readme) {
          fetchCache.set(cacheKey, { content: readme.text, title: readme.title, extractor: 'github-readme', timestamp: Date.now() });
          return JSON.stringify({
            url, prompt,
            title: readme.title,
            content: readme.text,
            extractor: 'github-readme',
            tookMs: Date.now() - start,
            cached: false,
          });
        }
      }

      // General fetch
      const response = await fetch(url, {
        headers: {
          'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
          Accept: 'text/html, text/plain, */*',
        },
        signal: AbortSignal.timeout(30_000),
      });

      if (!response.ok) {
        return JSON.stringify({ error: `HTTP ${response.status}: ${response.statusText}`, url });
      }

      const contentType = response.headers.get('content-type') ?? '';
      const contentLength = Number(response.headers.get('content-length') ?? '0');
      if (contentLength > MAX_RESPONSE_BYTES) {
        return JSON.stringify({
          error: `Page too large (${Math.round(contentLength / 1024)}KB). Max is ${MAX_RESPONSE_BYTES / 1024}KB.`,
          url,
        });
      }

      const raw = await response.text();
      let title = '';
      let text = '';
      let extractor = 'raw';

      if (contentType.includes('text/markdown')) {
        // Server returned markdown directly (e.g. Cloudflare Markdown for Agents)
        text = raw;
        extractor = 'markdown';
      } else if (contentType.includes('text/html') || raw.trimStart().startsWith('<!doctype') || raw.trimStart().startsWith('<html')) {
        // Try Readability first (Firefox reader mode algorithm)
        const readable = await extractReadableContent(raw, url);
        if (readable?.text) {
          title = readable.title;
          text = readable.text;
          extractor = 'readability';
        } else {
          // Fallback to basic HTML→markdown
          const basic = basicHtmlToMarkdown(raw);
          title = basic.title;
          text = basic.text;
          extractor = 'basic-html';
        }
      } else if (contentType.includes('application/json')) {
        try {
          text = JSON.stringify(JSON.parse(raw), null, 2);
          extractor = 'json';
        } catch {
          text = raw;
        }
      } else {
        text = raw;
      }

      // Truncate
      if (text.length > MAX_CONTENT_CHARS) {
        text = text.slice(0, MAX_CONTENT_CHARS) + '\n\n... [truncated]';
      }

      fetchCache.set(cacheKey, { content: text, title, extractor, timestamp: Date.now() });

      return JSON.stringify({
        url, prompt,
        title,
        content: text,
        extractor,
        contentType,
        tookMs: Date.now() - start,
        cached: false,
      });
    } catch (err) {
      return JSON.stringify({ error: `Web fetch failed: ${err instanceof Error ? err.message : String(err)}`, url });
    }
  };
}

// ---- static tool entry ----

const webFetchHandler: ToolHandler = createWebFetchHandler();

export const webFetchTool: ToolEntry = {
  name: 'web_fetch',
  toolset: 'web',
  schema: webFetchSchema,
  handler: webFetchHandler,
  isAsync: true,
  emoji: '📄',
  maxResultSizeChars: MAX_CONTENT_CHARS,
};
