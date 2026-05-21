// ============================================================================
// Builtin tool tests — bash + read_file (more thorough) + write/edit/glob/grep (smoke)
// ============================================================================

import { describe, it, expect } from 'vitest';
import type { ToolHandler, ToolContext } from '../registry.js';
import { bashTool } from '../builtin/bash.js';
import { readFileTool } from '../builtin/file-read.js';
import { writeFileTool } from '../builtin/file-write.js';
import { editFileTool } from '../builtin/file-edit.js';
import { globTool } from '../builtin/glob.js';
import { grepTool } from '../builtin/grep.js';
import { webSearchTool } from '../builtin/web-search.js';
import { webFetchTool } from '../builtin/web-fetch.js';

const ctx: ToolContext = {};

// ============================================================================
// Bash tool
// ============================================================================

describe('bash tool', () => {
  it('schema has correct format', () => {
    expect(bashTool.name).toBe('bash');
    expect(bashTool.schema.type).toBe('function');
    const fn = bashTool.schema.function as Record<string, unknown>;
    expect(fn.name).toBe('bash');
    expect(fn.parameters).toBeDefined();
  });

  it('executes a simple echo command', async () => {
    const result = await bashTool.handler({ command: 'echo hello' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.exitCode).toBe(0);
    expect(parsed.stdout).toContain('hello');
  });

  it('captures stderr', async () => {
    // Command that outputs to stderr
    const result = await bashTool.handler(
      { command: 'echo error >&2' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.stderr).toContain('error');
  });

  it('handles command not found', async () => {
    const result = await bashTool.handler(
      { command: 'nonexistent_command_xyz_123' },
      ctx,
    );
    const parsed = JSON.parse(result);
    // Non-zero exit on command-not-found
    expect(parsed.exitCode).not.toBe(0);
  });

  it('handles empty command', async () => {
    const result = await bashTool.handler({ command: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No command provided');
  });
});

// ============================================================================
// Read file tool
// ============================================================================

describe('read_file tool', () => {
  it('schema has correct format', () => {
    expect(readFileTool.name).toBe('read_file');
    expect(readFileTool.schema.type).toBe('function');
  });

  it('reads a known file with line numbers', async () => {
    // Read the package.json of the tools package itself
    const result = await readFileTool.handler(
      { path: 'D:/agent/Jarvis/packages/tools/package.json' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.content).toBeDefined();
    expect(parsed.content).toContain('@jarvis/tools');
    expect(parsed.totalLines).toBeGreaterThan(0);
  });

  it('applies offset correctly', async () => {
    const result = await readFileTool.handler(
      {
        path: 'D:/agent/Jarvis/packages/tools/package.json',
        offset: 3,
        limit: 1,
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.content).toBeDefined();
    // Line 3 should be the version line
    expect(parsed.content).toContain('"version"');
    expect(parsed.linesRead).toBe(1);
  });

  it('returns error for missing file', async () => {
    const result = await readFileTool.handler(
      { path: 'D:/agent/Jarvis/packages/tools/nonexistent_file.txt' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('File not found');
  });

  it('handles empty path', async () => {
    const result = await readFileTool.handler({ path: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No path provided');
  });

  it('handles offset beyond file length', async () => {
    const result = await readFileTool.handler(
      {
        path: 'D:/agent/Jarvis/packages/tools/package.json',
        offset: 99999,
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.message).toContain('Offset');
  });

  it('has cat -n format (tab-separated line numbers)', async () => {
    const result = await readFileTool.handler(
      { path: 'D:/agent/Jarvis/packages/tools/package.json', limit: 2 },
      ctx,
    );
    const parsed = JSON.parse(result);
    const lines = parsed.content.split('\n');
    for (const line of lines.slice(0, 1)) {
      // Should have a tab character separating line number from content
      expect(line).toMatch(/^\s+\d+\t/);
    }
  });
});

// ============================================================================
// Write file tool (smoke tests)
// ============================================================================

describe('write_file tool', () => {
  it('schema has correct format', () => {
    expect(writeFileTool.name).toBe('write_file');
    expect(writeFileTool.schema.type).toBe('function');
  });

  it('rejects empty path', async () => {
    const result = await writeFileTool.handler({ path: '', content: 'test' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No path provided');
  });
});

// ============================================================================
// Edit file tool (smoke tests)
// ============================================================================

describe('edit_file tool', () => {
  it('schema has correct format', () => {
    expect(editFileTool.name).toBe('edit_file');
    expect(editFileTool.schema.type).toBe('function');
  });

  it('rejects missing file', async () => {
    const result = await editFileTool.handler(
      { path: '/nonexistent/file.txt', old_string: 'a', new_string: 'b' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('File not found');
  });
});

// ============================================================================
// Glob tool
// ============================================================================

describe('glob tool', () => {
  it('schema has correct format', () => {
    expect(globTool.name).toBe('glob');
    expect(globTool.schema.type).toBe('function');
  });

  it('finds files with *.json pattern', async () => {
    const result = await globTool.handler(
      { pattern: '*.json', path: 'D:/agent/Jarvis/packages/tools' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    expect(Array.isArray(parsed.matches)).toBe(true);
    // Should find package.json at minimum
    expect(parsed.matches).toContain('package.json');
  });

  it('finds files with ** pattern', async () => {
    const result = await globTool.handler(
      { pattern: '**/*.ts', path: 'D:/agent/Jarvis/packages/tools/src' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    // Should find at least index.ts and registry.ts
    expect(parsed.matches.some((m: string) => m.endsWith('index.ts'))).toBe(true);
    expect(parsed.matches.some((m: string) => m.endsWith('registry.ts'))).toBe(true);
  });

  it('rejects empty pattern', async () => {
    const result = await globTool.handler({ pattern: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No pattern provided');
  });
});

// ============================================================================
// Grep tool
// ============================================================================

describe('grep tool', () => {
  it('schema has correct format', () => {
    expect(grepTool.name).toBe('grep');
    expect(grepTool.schema.type).toBe('function');
  });

  it('finds text matching a pattern', async () => {
    const result = await grepTool.handler(
      { pattern: 'ToolRegistry', path: 'D:/agent/Jarvis/packages/tools/src' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    expect(Array.isArray(parsed.matches)).toBe(true);
    expect(parsed.matches.length).toBeGreaterThan(0);
    for (const match of parsed.matches) {
      expect(match).toContain('ToolRegistry');
    }
  });

  it('supports files_with_matches mode', async () => {
    const result = await grepTool.handler(
      {
        pattern: 'export.*ToolRegistry',
        path: 'D:/agent/Jarvis/packages/tools/src',
        output_mode: 'files_with_matches',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.files).toBeDefined();
    expect(Array.isArray(parsed.files)).toBe(true);
    expect(parsed.files.length).toBeGreaterThan(0);
  });

  it('rejects empty pattern', async () => {
    const result = await grepTool.handler({ pattern: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No pattern provided');
  });

  it('rejects invalid regex', async () => {
    const result = await grepTool.handler({ pattern: '[invalid[', path: '/tmp' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Invalid regex');
  });
});

// ============================================================================
// Web search tool (stub)
// ============================================================================

describe('web_search tool', () => {
  it('returns error about API key configuration', async () => {
    const result = await webSearchTool.handler({ query: 'test' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('API key configuration');
    expect(parsed.error).toContain('SEARCH_API_KEY');
  });

  it('has correct requiresEnv for availability check', () => {
    expect(webSearchTool.requiresEnv).toContain('SEARCH_API_KEY');
  });
});

// ============================================================================
// Web fetch tool (stub)
// ============================================================================

describe('web_fetch tool', () => {
  it('returns error about API key configuration', async () => {
    const result = await webFetchTool.handler({ url: 'http://example.com', prompt: 'test' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('API key configuration');
    expect(parsed.error).toContain('JARVIS_WEB_API_KEY');
  });

  it('is marked async', () => {
    expect(webFetchTool.isAsync).toBe(true);
  });
});
