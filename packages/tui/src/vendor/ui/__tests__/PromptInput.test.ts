import { describe, expect, it } from 'vitest';
import { filterCommands } from '../utils/promptInputLogic.js';

const commands = [
  { name: 'help', description: 'Show available commands' },
  { name: 'clear', description: 'Clear conversation history' },
  { name: 'context', description: 'Show current session context info' },
  { name: 'compact', description: 'Summarize conversation history' },
  { name: 'config', description: 'Show or set configuration' },
  { name: 'model', description: 'Show or set the current model' },
  { name: 'memory', description: 'Show or search project memory' },
  { name: 'mcp', description: 'Show MCP server diagnostics' },
  { name: 'mode', description: 'Show or switch permission mode' },
  { name: 'effort', description: 'Show or set reasoning effort' },
];

describe('filterCommands', () => {
  it('returns all commands for bare /', () => {
    const result = filterCommands(commands, '/');
    expect(result.length).toBe(commands.length);
  });

  it('returns empty for non-slash input', () => {
    expect(filterCommands(commands, 'hello')).toEqual([]);
  });

  it('filters by prefix and description match', () => {
    const result = filterCommands(commands, '/co');
    const names = result.map((c) => c.name);
    // Prefix matches (score 80)
    expect(names).toContain('context');
    expect(names).toContain('compact');
    expect(names).toContain('config');
    // 'help' matches via description "Show available commands" (score 20)
    expect(names).toContain('help');
  });

  it('exact match scores highest', () => {
    const result = filterCommands(commands, '/help');
    expect(result[0].name).toBe('help');
  });

  it('prefix match scores higher than description match', () => {
    const result = filterCommands(commands, '/mo');
    const names = result.map((c) => c.name);
    // Prefix matches (score 80) come first
    expect(names[0]).toBe('model');
    expect(names[1]).toBe('mode');
    // 'memory' has 'mo' as substring (score ~50) — appears after prefix matches
    expect(names).toContain('memory');
    // Verify ordering: prefix matches before substring matches
    const modelIdx = names.indexOf('model');
    const modeIdx = names.indexOf('mode');
    const memoryIdx = names.indexOf('memory');
    expect(modelIdx).toBeLessThan(memoryIdx);
    expect(modeIdx).toBeLessThan(memoryIdx);
  });

  it('same-prefix commands have stable ordering', () => {
    // Run twice to verify consistency
    const result1 = filterCommands(commands, '/c');
    const result2 = filterCommands(commands, '/c');
    expect(result1.map((c) => c.name)).toEqual(result2.map((c) => c.name));
  });

  it('returns max 50 results', () => {
    const manyCommands = Array.from({ length: 60 }, (_, i) => ({
      name: `cmd${i}`,
      description: 'test',
    }));
    const result = filterCommands(manyCommands, '/');
    expect(result.length).toBe(50);
  });
});
