import { describe, it, expect } from 'vitest';
import {
  toOpenAITool,
  sanitizeToolSchemas,
} from '../schemas.js';
import type { ToolSchemaDef } from '../schemas.js';
import {
  detectPlatform,
  getJarvisHome,
  getDefaultShell,
} from '../env.js';

// ============================================================================
// Schema helpers
// ============================================================================

describe('toOpenAITool', () => {
  it('wraps a schema in OpenAI function format', () => {
    const def: ToolSchemaDef = {
      name: 'read_file',
      description: 'Read a file from disk',
      parameters: {
        type: 'object',
        properties: {
          path: { type: 'string', description: 'File path' },
        },
        required: ['path'],
      },
    };

    const result = toOpenAITool(def);

    expect(result).toEqual({
      type: 'function',
      function: {
        name: 'read_file',
        description: 'Read a file from disk',
        parameters: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'File path' },
          },
          required: ['path'],
        },
      },
    });
  });

  it('handles schemas with no parameters', () => {
    const def: ToolSchemaDef = {
      name: 'ping',
      description: 'Check connectivity',
      parameters: {},
    };

    const result = toOpenAITool(def);

    expect(result).toEqual({
      type: 'function',
      function: {
        name: 'ping',
        description: 'Check connectivity',
        parameters: {},
      },
    });
  });
});

describe('sanitizeToolSchemas', () => {
  it('converts bare string type to object', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              name: 'string', // bare string type
            },
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (
      (result[0] as Record<string, unknown>).function as Record<string, unknown>
    ).parameters as Record<string, unknown>;
    const props = param.properties as Record<string, unknown>;

    // Bare string should become { type: "string" }
    expect(props.name).toEqual({ type: 'string' });
  });

  it('strips union-with-null types', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              age: { type: ['number', 'null'] },
            },
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (
      (result[0] as Record<string, unknown>).function as Record<string, unknown>
    ).parameters as Record<string, unknown>;
    const props = param.properties as Record<string, unknown>;

    // type: [X, "null"] should be removed
    expect((props.age as Record<string, unknown>).type).toBeUndefined();
  });

  it('adds empty properties to objects missing it', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              config: { type: 'object' }, // no properties field
            },
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (
      (result[0] as Record<string, unknown>).function as Record<string, unknown>
    ).parameters as Record<string, unknown>;
    const props = param.properties as Record<string, unknown>;
    const config = props.config as Record<string, unknown>;

    expect(config.properties).toEqual({});
  });

  it('removes required entries that do not match any property', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              path: { type: 'string' },
            },
            required: ['path', 'missing_field'],
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (
      (result[0] as Record<string, unknown>).function as Record<string, unknown>
    ).parameters as Record<string, unknown>;

    expect(param.required).toEqual(['path']);
  });

  it('removes required entirely when no entries match', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              path: { type: 'string' },
            },
            required: ['missing1', 'missing2'],
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (
      (result[0] as Record<string, unknown>).function as Record<string, unknown>
    ).parameters as Record<string, unknown>;

    expect(param.required).toBeUndefined();
  });

  it('does not mutate the original input', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              name: 'string',
            },
          },
        },
      },
    ];

    const copy = JSON.parse(JSON.stringify(tools));
    sanitizeToolSchemas(tools);

    // Original should be unchanged
    expect(tools).toEqual(copy);
  });

  it('handles nested schemas recursively', () => {
    const tools = [
      {
        function: {
          name: 'test',
          parameters: {
            type: 'object',
            properties: {
              outer: {
                type: 'object',
                properties: {
                  inner: 'string', // bare string in nested object
                },
              },
            },
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (
      (result[0] as Record<string, unknown>).function as Record<string, unknown>
    ).parameters as Record<string, unknown>;
    const props = param.properties as Record<string, unknown>;
    const outer = props.outer as Record<string, unknown>;
    const outerProps = outer.properties as Record<string, unknown>;

    expect(outerProps.inner).toEqual({ type: 'string' });
  });

  it('handles missing function wrapper (direct schema)', () => {
    const tools = [
      {
        name: 'test',
        parameters: {
          type: 'object',
          properties: {
            name: 'string',
          },
        },
      },
    ];

    const result = sanitizeToolSchemas(tools);
    const param = (result[0] as Record<string, unknown>)
      .parameters as Record<string, unknown>;
    const props = param.properties as Record<string, unknown>;

    expect(props.name).toEqual({ type: 'string' });
  });
});

// ============================================================================
// Env helpers
// ============================================================================

describe('detectPlatform', () => {
  it('returns a known platform string', () => {
    const plat = detectPlatform();
    expect(['windows', 'linux', 'macos']).toContain(plat);
  });

  it('matches process.platform', () => {
    const plat = detectPlatform();
    if (process.platform === 'win32') expect(plat).toBe('windows');
    if (process.platform === 'darwin') expect(plat).toBe('macos');
    if (process.platform === 'linux') expect(plat).toBe('linux');
  });
});

describe('getJarvisHome', () => {
  it('returns a string ending with .jarvis when JARVIS_HOME is not set', () => {
    delete process.env.JARVIS_HOME;
    const home = getJarvisHome();
    expect(home).toBeTruthy();
    expect(home.endsWith('.jarvis')).toBe(true);
  });

  it('respects JARVIS_HOME env var', () => {
    process.env.JARVIS_HOME = '/custom/path';
    expect(getJarvisHome()).toBe('/custom/path');
    delete process.env.JARVIS_HOME;
  });
});

describe('getDefaultShell', () => {
  it('returns a truthy string', () => {
    const shell = getDefaultShell();
    expect(shell).toBeTruthy();
    expect(typeof shell).toBe('string');
  });

  it('returns powershell.exe on Windows (default, without SHELL set)', () => {
    const originalShell = process.env.SHELL;
    delete process.env.SHELL;

    // Platform is win32 on this test runner
    if (process.platform === 'win32') {
      expect(getDefaultShell()).toBe('powershell.exe');
    }

    process.env.SHELL = originalShell;
    // process.platform can't be overridden, so only test on actual Windows
  });

  it('respects SHELL env var', () => {
    process.env.SHELL = '/bin/zsh';
    expect(getDefaultShell()).toBe('/bin/zsh');
    delete process.env.SHELL;
  });
});

// ============================================================================
// Type compile-time checks (verified by tsc, not runtime)
// ============================================================================

describe('type exports', () => {
  it('all expected modules can be imported', async () => {
    // Dynamic import to verify barrel exports resolve
    const shared = await import('../index.js');
    expect(shared.toOpenAITool).toBeDefined();
    expect(shared.sanitizeToolSchemas).toBeDefined();
    expect(shared.detectPlatform).toBeDefined();
    expect(shared.getJarvisHome).toBeDefined();
    expect(shared.getDefaultShell).toBeDefined();
    expect(shared.isWSL).toBeDefined();
    expect(shared.isContainer).toBeDefined();
  });
});
