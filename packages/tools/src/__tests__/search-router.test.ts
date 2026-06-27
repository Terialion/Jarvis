import { describe, expect, it } from 'vitest';
import {
  buildSearchRoutePlan,
  searchRouterTool,
} from '../builtin/search-router.js';

const skillSupplier = {
  listLoadable() {
    return [
      { name: 'multi-search-engine', description: 'Search the web using multiple engines.' },
      { name: 'earnings-tracker', description: 'Track earnings reports.' },
    ];
  },
};

const mcpTools = [
  'mcp__tavily_mcp__tavily_search',
  'mcp__browser__web_search',
  'mcp__browser__fetch_url',
];

describe('search router', () => {
  it('prefers search skills and MCP before provider-specific Tavily', () => {
    const plan = buildSearchRoutePlan({
      query: 'latest AI coding agents comparison',
      availableSkills: skillSupplier.listLoadable(),
      availableToolNames: ['web_search', 'web_fetch', 'tavily_search', 'tavily_fetch', ...mcpTools],
      tavilyAvailable: true,
    });

    expect(plan.routes.map((route) => route.kind)).toEqual(['skill', 'mcp', 'web', 'tavily']);
    expect(plan.routes[0]?.tool).toBe('skill.load');
    expect(plan.routes[0]?.target).toBe('multi-search-engine');
    expect(plan.routes.at(-1)?.reason).toContain('provider-specific');
  });

  it('falls back to general web tools when no search skill or MCP tool is available', () => {
    const plan = buildSearchRoutePlan({
      query: 'typescript release notes',
      availableSkills: [],
      availableToolNames: ['web_search', 'web_fetch'],
      tavilyAvailable: false,
    });

    expect(plan.routes.map((route) => route.kind)).toEqual(['web']);
    expect(plan.routes[0]?.tools).toEqual(['web_search', 'web_fetch']);
  });

  it('returns a JSON route plan from the tool handler', async () => {
    const result = await searchRouterTool.handler(
      {
        query: '大明王朝1566 名句',
        available_skills: skillSupplier.listLoadable(),
        available_tools: ['web_search', 'web_fetch', ...mcpTools],
      },
      {},
    );

    const parsed = JSON.parse(result);
    expect(parsed.query).toBe('大明王朝1566 名句');
    expect(parsed.routes[0].kind).toBe('skill');
    expect(parsed.routes.some((route: { kind: string }) => route.kind === 'mcp')).toBe(true);
  });
});
