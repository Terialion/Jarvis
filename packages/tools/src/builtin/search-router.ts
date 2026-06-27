// ============================================================================
// Search router - builds a source plan across skills, MCP, web, and Tavily.
// This tool does not perform network I/O; it tells the model which search
// source to use first so provider-specific tools do not become the default.
// ============================================================================

import { toOpenAITool } from '@jarvis/shared';
import type { ToolEntry, ToolHandler } from '../registry.js';

export type SearchRouteKind = 'skill' | 'mcp' | 'web' | 'tavily';

export type SearchRoute = {
  kind: SearchRouteKind;
  tool?: string;
  tools?: string[];
  target?: string;
  reason: string;
};

export type SearchRoutePlan = {
  query: string;
  routes: SearchRoute[];
  guidance: string[];
};

export type SearchRouteSkill = {
  name: string;
  description?: string;
};

export type SearchRouteInput = {
  query: string;
  availableSkills?: SearchRouteSkill[];
  availableToolNames?: string[];
  tavilyAvailable?: boolean;
};

function normalize(value: string): string {
  return value.toLowerCase().replace(/[_-]+/g, ' ');
}

function isSearchSkill(skill: SearchRouteSkill): boolean {
  const haystack = normalize(`${skill.name} ${skill.description ?? ''}`);
  return /\b(search|web|browser|crawl|research|fetch|tavily|bing|google|duckduckgo)\b/.test(haystack);
}

function isMcpSearchTool(toolName: string): boolean {
  const normalized = normalize(toolName);
  return normalized.startsWith('mcp ') && /\b(search|fetch|extract|browser|crawl|web|tavily)\b/.test(normalized);
}

function pickTools(availableToolNames: string[], names: string[]): string[] {
  const available = new Set(availableToolNames);
  return names.filter((name) => available.has(name));
}

export function buildSearchRoutePlan(input: SearchRouteInput): SearchRoutePlan {
  const query = input.query.trim();
  const availableSkills = input.availableSkills ?? [];
  const availableToolNames = input.availableToolNames ?? [];
  const routes: SearchRoute[] = [];

  const searchSkill = availableSkills.find(isSearchSkill);
  if (searchSkill) {
    routes.push({
      kind: 'skill',
      tool: 'skill.load',
      target: searchSkill.name,
      reason: 'A search-related skill is available; load it first so its workflow can coordinate engines and source handling.',
    });
  }

  const mcpSearchTools = availableToolNames.filter(isMcpSearchTool);
  if (mcpSearchTools.length > 0) {
    routes.push({
      kind: 'mcp',
      tools: mcpSearchTools,
      reason: 'MCP search/fetch tools are available; use them when they provide authenticated, configured, or specialized sources.',
    });
  }

  const generalWebTools = pickTools(availableToolNames, ['web_search', 'web_fetch']);
  if (generalWebTools.length > 0) {
    routes.push({
      kind: 'web',
      tools: generalWebTools,
      reason: 'General web tools are the default route for ordinary public web research.',
    });
  }

  const tavilyTools = pickTools(availableToolNames, ['tavily_search', 'tavily_fetch']);
  if (input.tavilyAvailable || tavilyTools.length > 0) {
    routes.push({
      kind: 'tavily',
      tools: tavilyTools.length > 0 ? tavilyTools : ['tavily_search', 'tavily_fetch'],
      reason: 'Tavily is provider-specific; use it when explicitly requested, for provider comparison, or as a fallback if the preferred routes fail.',
    });
  }

  return {
    query,
    routes,
    guidance: [
      'Do not use Tavily as the default just because it is available.',
      'Prefer skill workflow + MCP where relevant, then general web tools, then provider-specific fallback/cross-check.',
      'After gathering results, cite source URLs and mention which route was used when it matters.',
    ],
  };
}

export const searchRouterSchema = toOpenAITool({
  name: 'search_router',
  description:
    'Plan which search source to use across search-related skills, MCP search/fetch tools, general web_search/web_fetch, and provider-specific Tavily. This returns a route plan; it does not perform the search.',
  parameters: {
    type: 'object',
    properties: {
      query: { type: 'string', description: 'The research query or user request.' },
      available_skills: {
        type: 'array',
        description: 'Optional list of available skills with name and description.',
        items: {
          type: 'object',
          properties: {
            name: { type: 'string' },
            description: { type: 'string' },
          },
          required: ['name'],
        },
      },
      available_tools: {
        type: 'array',
        description: 'Optional list of currently available tool names.',
        items: { type: 'string' },
      },
      tavily_available: {
        type: 'boolean',
        description: 'Whether Tavily provider tools are configured even if not listed in available_tools.',
      },
    },
    required: ['query'],
  },
});

function parseSkills(value: unknown): SearchRouteSkill[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((entry) => {
      if (typeof entry === 'string') return { name: entry };
      if (!entry || typeof entry !== 'object') return null;
      const raw = entry as Record<string, unknown>;
      const name = String(raw.name ?? '').trim();
      if (!name) return null;
      return {
        name,
        description: typeof raw.description === 'string' ? raw.description : undefined,
      };
    })
    .filter((entry): entry is SearchRouteSkill => Boolean(entry));
}

function parseToolNames(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(String).map((name) => name.trim()).filter(Boolean);
}

const searchRouterHandler: ToolHandler = (args) => {
  const query = String(args.query ?? '').trim();
  if (!query) {
    return JSON.stringify({ error: 'Missing required parameter: query' });
  }

  return JSON.stringify(buildSearchRoutePlan({
    query,
    availableSkills: parseSkills(args.available_skills ?? args.availableSkills),
    availableToolNames: parseToolNames(args.available_tools ?? args.availableToolNames),
    tavilyAvailable: Boolean(args.tavily_available ?? args.tavilyAvailable),
  }));
};

export const searchRouterTool: ToolEntry = {
  name: 'search_router',
  toolset: 'web',
  schema: searchRouterSchema,
  handler: searchRouterHandler,
  isAsync: false,
  emoji: 'SR',
  maxResultSizeChars: 20_000,
};
