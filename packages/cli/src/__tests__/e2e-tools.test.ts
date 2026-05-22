import { describe, it, expect, beforeAll } from 'vitest';
import { ToolRegistry, allBuiltinTools } from '@jarvis/tools';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const testDir = path.dirname(fileURLToPath(import.meta.url));
// testDir is .../packages/cli/src/__tests__, repoRoot is 4 levels up
const repoRoot = path.resolve(testDir, '..', '..', '..', '..');

describe('E2E: Tools', () => {
  const registry = new ToolRegistry();

  beforeAll(() => {
    for (const tool of allBuiltinTools) {
      registry.register(tool);
    }
  });

  it('registers all 8 builtin tools', () => {
    const names = registry.getAllToolNames().sort();
    expect(names).toContain('bash');
    expect(names).toContain('read_file');
    expect(names).toContain('write_file');
    expect(names).toContain('edit_file');
    expect(names).toContain('glob');
    expect(names).toContain('grep');
    expect(names).toContain('web_fetch');
    expect(names).toContain('web_search');
  });

  it('bash: executes echo command', async () => {
    const result = await registry.dispatch('bash', { command: 'echo hello_from_bash' });
    expect(result).toContain('hello_from_bash');
  });

  it('bash: returns current directory', async () => {
    const result = await registry.dispatch('bash', { command: 'pwd' });
    expect(result.trim().length).toBeGreaterThan(0);
  });

  it('read_file: reads root package.json', async () => {
    const target = path.join(repoRoot, 'package.json');
    const result = await registry.dispatch('read_file', { path: target });
    const parsed = JSON.parse(result);
    expect(parsed.content).toBeDefined();
    expect(parsed.totalLines).toBeGreaterThan(0);
  });

  it('write_file: writes and verifies temp file', async () => {
    const tmpFile = path.join(testDir, '_e2e_tmp.txt');
    const content = 'jarvis e2e test write';
    const writeResult = await registry.dispatch('write_file', { path: tmpFile, content });
    const writeParsed = JSON.parse(writeResult);
    expect(writeParsed.ok).toBe(true);
    expect(fs.existsSync(tmpFile)).toBe(true);
    expect(fs.readFileSync(tmpFile, 'utf-8')).toBe(content);
    fs.unlinkSync(tmpFile);
  });

  it('glob: finds package.json files', async () => {
    const packagesDir = path.join(repoRoot, 'packages');
    const result = await registry.dispatch('glob', {
      pattern: '*/package.json',
      path: packagesDir,
    });
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    expect(parsed.matches.length).toBeGreaterThanOrEqual(11);
    expect(parsed.matches.some((m: string) => m.endsWith('cli/package.json'))).toBe(true);
    expect(parsed.matches.some((m: string) => m.endsWith('agent/package.json'))).toBe(true);
  });

  it('grep: finds AgentLoop class', async () => {
    const agentSrc = path.join(repoRoot, 'packages', 'agent', 'src');
    const result = await registry.dispatch('grep', {
      pattern: 'AgentLoop',
      path: agentSrc,
    });
    expect(result).toContain('AgentLoop');
  });

  it('write_file + read_file round-trip', async () => {
    const tmpFile = path.join(testDir, '_e2e_roundtrip.txt');
    const content = 'round trip test data\nline2';
    await registry.dispatch('write_file', { path: tmpFile, content });
    const readBackRaw = await registry.dispatch('read_file', { path: tmpFile });
    const readBack = JSON.parse(readBackRaw);
    const strippedContent = readBack.content
      .split('\n')
      .map((line: string) => line.slice(7))
      .join('\n');
    expect(strippedContent).toBe(content);
    fs.unlinkSync(tmpFile);
  });
});
