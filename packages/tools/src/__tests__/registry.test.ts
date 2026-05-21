// ============================================================================
// ToolRegistry tests
// ============================================================================

import { describe, it, expect, beforeEach } from 'vitest';
import { ToolRegistry, type ToolEntry, type ToolHandler } from '../registry.js';
import { toOpenAITool } from '@jarvis/shared';
import { bashSchema } from '../builtin/bash.js';
import { readFileSchema } from '../builtin/file-read.js';

// Helper: create a simple test tool entry
function makeEntry(
  overrides: Partial<ToolEntry> = {},
): ToolEntry {
  const name = overrides.name ?? 'test_tool';
  const base: ToolEntry = {
    name,
    toolset: 'test',
    schema: toOpenAITool({
      name,
      description: overrides.description ?? 'A test tool',
      parameters: { type: 'object', properties: {} },
    }),
    handler: () => JSON.stringify({ ok: true }),
  };
  return { ...base, ...overrides };
}

describe('ToolRegistry', () => {
  let registry: ToolRegistry;

  beforeEach(() => {
    registry = new ToolRegistry();
  });

  // ---- register ----

  it('registers a tool and retrieves it', () => {
    const entry = makeEntry({ name: 'my_tool' });
    registry.register(entry);
    expect(registry.getEntry('my_tool')).toBe(entry);
    expect(registry.size()).toBe(1);
  });

  it('throws on duplicate registration', () => {
    registry.register(makeEntry({ name: 'dup', toolset: 'test' }));
    expect(() =>
      registry.register(makeEntry({ name: 'dup', toolset: 'other' })),
    ).toThrow(/already registered/);
  });

  it('allows MCP override (both toolsets start with mcp-)', () => {
    registry.register(makeEntry({ name: 'mcp_server', toolset: 'mcp-server-a' }));
    const override = makeEntry({ name: 'mcp_server', toolset: 'mcp-server-b' });
    expect(() => registry.register(override)).not.toThrow();
    expect(registry.getEntry('mcp_server')).toBe(override);
  });

  it('does not allow non-mcp override of MCP tool', () => {
    registry.register(makeEntry({ name: 'mcp_server', toolset: 'mcp-server-a' }));
    expect(() =>
      registry.register(makeEntry({ name: 'mcp_server', toolset: 'builtin' })),
    ).toThrow(/already registered/);
  });

  // ---- getEntry ----

  it('returns undefined for unknown tool', () => {
    expect(registry.getEntry('nonexistent')).toBeUndefined();
  });

  // ---- dispatch ----

  it('dispatches to handler and returns result', async () => {
    registry.register(
      makeEntry({
        name: 'echo',
        handler: (args) => JSON.stringify({ echo: args.message }),
      }),
    );
    const result = await registry.dispatch('echo', { message: 'hello' });
    expect(JSON.parse(result)).toEqual({ echo: 'hello' });
  });

  it('returns error JSON for unknown tool', async () => {
    const result = await registry.dispatch('nope', {});
    expect(JSON.parse(result)).toEqual({ error: 'Tool not found: "nope"' });
  });

  it('catches handler exceptions and returns error JSON', async () => {
    registry.register(
      makeEntry({
        name: 'exploder',
        handler: () => {
          throw new Error('BOOM');
        },
      }),
    );
    const result = await registry.dispatch('exploder', {});
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Tool execution failed');
    expect(parsed.error).toContain('BOOM');
  });

  // NEVER throws — even for catastrophic errors
  it('NEVER throws — not even for catastrophic errors', async () => {
    registry.register(
      makeEntry({
        name: 'catastrophic',
        handler: () => {
          // Simulate a non-Error throw
          throw 'raw string error';
        },
      }),
    );
    // This must not throw
    const result = await registry.dispatch('catastrophic', {});
    expect(() => JSON.parse(result)).not.toThrow();
    expect(JSON.parse(result).error).toBeDefined();
  });

  // ---- async support ----

  it('supports async handlers', async () => {
    registry.register(
      makeEntry({
        name: 'async_tool',
        isAsync: true,
        handler: async (args) => {
          return JSON.stringify({ waited: true });
        },
      }),
    );
    const result = await registry.dispatch('async_tool', {});
    expect(JSON.parse(result)).toEqual({ waited: true });
  });

  // ---- getDefinitions ----

  it('returns OpenAI-format definitions', () => {
    registry.register(makeEntry({ name: 'tool_a' }));
    registry.register(makeEntry({ name: 'tool_b' }));
    const defs = registry.getDefinitions();
    expect(defs).toHaveLength(2);
    for (const def of defs) {
      expect(def.type).toBe('function');
      const fn = (def as Record<string, unknown>).function as Record<string, unknown>;
      expect(fn.name).toBeDefined();
      expect(fn.description).toBeDefined();
      expect(fn.parameters).toBeDefined();
    }
  });

  it('filters by checkFn', () => {
    registry.register(makeEntry({ name: 'available' }));
    registry.register(
      makeEntry({
        name: 'unavailable',
        checkFn: () => false,
      }),
    );
    const defs = registry.getDefinitions();
    expect(defs).toHaveLength(1);
    const fn = (defs[0] as Record<string, unknown>).function as Record<string, unknown>;
    expect(fn.name).toBe('available');
  });

  it('filters by requiresEnv', () => {
    registry.register(makeEntry({ name: 'needs_key', requiresEnv: ['MYTHICAL_KEY'] }));
    const defs = registry.getDefinitions();
    expect(defs).toHaveLength(0);
  });

  it('filters by toolNames whitelist', () => {
    registry.register(makeEntry({ name: 'a' }));
    registry.register(makeEntry({ name: 'b' }));
    registry.register(makeEntry({ name: 'c' }));
    const defs = registry.getDefinitions(['a', 'c']);
    expect(defs).toHaveLength(2);
  });

  // ---- getToolNamesByToolset ----

  it('groups tools by toolset', () => {
    registry.register(makeEntry({ name: 'bash', toolset: 'terminal' }));
    registry.register(makeEntry({ name: 'read_file', toolset: 'file' }));
    registry.register(makeEntry({ name: 'write_file', toolset: 'file' }));

    expect(registry.getToolNamesByToolset('terminal')).toEqual(['bash']);
    expect(registry.getToolNamesByToolset('file')).toEqual(['read_file', 'write_file']);
    expect(registry.getToolNamesByToolset('nonexistent')).toEqual([]);
  });

  // ---- size ----

  it('size reflects registration count', () => {
    expect(registry.size()).toBe(0);
    registry.register(makeEntry({ name: 'a' }));
    expect(registry.size()).toBe(1);
    registry.register(makeEntry({ name: 'b' }));
    expect(registry.size()).toBe(2);
  });

  // ---- getAllToolNames ----

  it('getAllToolNames returns all names', () => {
    registry.register(makeEntry({ name: 'x' }));
    registry.register(makeEntry({ name: 'y' }));
    expect(registry.getAllToolNames()).toEqual(['x', 'y']);
  });

  // ---- real schemas ----

  it('works with actual bash and read_file schemas', () => {
    const handler: ToolHandler = () => JSON.stringify({ ok: true });
    registry.register({
      name: 'bash',
      toolset: 'terminal',
      schema: bashSchema,
      handler,
    });
    registry.register({
      name: 'read_file',
      toolset: 'file',
      schema: readFileSchema,
      handler,
    });

    const defs = registry.getDefinitions();
    expect(defs).toHaveLength(2);

    const names = (defs as Array<Record<string, unknown>>).map(
      (d) => ((d as Record<string, unknown>).function as Record<string, unknown>).name,
    );
    expect(names).toContain('bash');
    expect(names).toContain('read_file');
  });
});
