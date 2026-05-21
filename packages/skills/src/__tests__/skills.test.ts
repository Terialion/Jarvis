import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';
import { SkillLoader, normalizeAllowedTools, inferRiskLevel, inferSourceType } from '../loader.js';
import { SkillRegistry } from '../registry.js';
import { SkillMatcher } from '../matcher.js';
import { SkillExecutor } from '../executor.js';
import type { SkillSpec } from '../models.js';

// ============================================================================
// Helpers
// ============================================================================

let tmpDir: string;

function createSkillFile(
  root: string,
  filename: string,
  name: string,
  extraFm: Record<string, string> = {},
  body = 'This is the skill body content.',
): string {
  fs.mkdirSync(root, { recursive: true });

  const fm = [
    '---',
    `name: ${name}`,
    `description: A skill called ${name}`,
    ...Object.entries(extraFm).map(([k, v]) => `${k}: ${v}`),
    '---',
    body,
  ].join('\n');

  const filePath = path.join(root, filename);
  fs.writeFileSync(filePath, fm);
  return filePath;
}

beforeEach(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'jarvis-skills-'));
});

afterEach(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

// ============================================================================
// SkillLoader
// ============================================================================

describe('SkillLoader', () => {
  let loader: SkillLoader;

  beforeEach(() => {
    loader = new SkillLoader();
  });

  it('parses a SKILL.md file with frontmatter', () => {
    const filePath = createSkillFile(
      tmpDir,
      'SKILL.md',
      'test-skill',
      { tags: 'testing, example', risk_level: 'read_only' },
    );

    const spec = loader.parseSkillFile(filePath, 'builtin');

    expect(spec).not.toBeNull();
    expect(spec!.name).toBe('test-skill');
    expect(spec!.description).toContain('A skill called test-skill');
    expect(spec!.source).toBe('builtin');
    expect(spec!.riskLevel).toBe('read_only');
    expect(spec!.enabled).toBe(true);
    expect(spec!.quarantined).toBe(false);
    expect(spec!.tags).toEqual(['testing', 'example']);
  });

  it('returns null for non-existent file', () => {
    expect(loader.parseSkillFile('/nope/SKILL.md', 'builtin')).toBeNull();
  });

  it('returns null when frontmatter has no name', () => {
    const filePath = path.join(tmpDir, 'SKILL.md');
    fs.writeFileSync(filePath, '---\ndescription: No name here\n---\nBody');

    expect(loader.parseSkillFile(filePath, 'builtin')).toBeNull();
  });

  it('handles quarantined and disabled flags', () => {
    const filePath = createSkillFile(
      tmpDir,
      'SKILL.md',
      'quar-skill',
      { quarantined: 'true', enabled: 'false', trust_level: '10' },
    );

    const spec = loader.parseSkillFile(filePath, 'project');

    expect(spec!.quarantined).toBe(true);
    expect(spec!.enabled).toBe(false);
    expect(spec!.trustLevel).toBe(10);
  });

  it('discovers SKILL.md files in nested directories', () => {
    const nested = path.join(tmpDir, 'a', 'b');
    fs.mkdirSync(nested, { recursive: true });
    createSkillFile(nested, 'SKILL.md', 'nested-skill');

    const skills = loader.discoverSkills(tmpDir, 'user');
    expect(skills).toHaveLength(1);
    expect(skills[0].name).toBe('nested-skill');
  });

  it('stops discovery at depth > 3', () => {
    const deep = path.join(tmpDir, 'a', 'b', 'c', 'd', 'e');
    fs.mkdirSync(deep, { recursive: true });
    createSkillFile(deep, 'SKILL.md', 'too-deep');

    // Should be at depth 5, which is > 3, so skipped
    const skills = loader.discoverSkills(tmpDir, 'user');
    expect(skills).toEqual([]);
  });

  it('skips files not named SKILL.md', () => {
    fs.writeFileSync(
      path.join(tmpDir, 'README.md'),
      '---\nname: not-a-skill\n---\nJust a readme',
    );

    const skills = loader.discoverSkills(tmpDir, 'user');
    expect(skills).toEqual([]);
  });

  it('tracks file modification time', () => {
    const filePath = createSkillFile(tmpDir, 'SKILL.md', 'mtime-test');
    const spec = loader.parseSkillFile(filePath, 'builtin');

    expect(spec!.mtimeMs).toBeGreaterThan(0);
  });
});

// ============================================================================
// normalizeAllowedTools
// ============================================================================

describe('normalizeAllowedTools', () => {
  it('returns empty array for undefined', () => {
    expect(normalizeAllowedTools(undefined)).toEqual([]);
  });

  it('splits by commas and spaces', () => {
    const result = normalizeAllowedTools('read, bash, glob');
    expect(result).toContain('read');
    expect(result).toContain('bash');
    expect(result).toContain('glob');
  });

  it('deduplicates', () => {
    const result = normalizeAllowedTools('read, read, bash');
    expect(result).toEqual(['read', 'bash']);
  });
});

// ============================================================================
// inferRiskLevel
// ============================================================================

describe('inferRiskLevel', () => {
  it('uses explicit risk_level', () => {
    expect(inferRiskLevel('command', [])).toBe('command');
    expect(inferRiskLevel('read_only', [])).toBe('read_only');
  });

  it('infers from allowed tools when no explicit level', () => {
    expect(inferRiskLevel(undefined, ['bash'])).toBe('command');
    expect(inferRiskLevel(undefined, ['web-fetch'])).toBe('network');
    expect(inferRiskLevel(undefined, ['write'])).toBe('write_approval_required');
    expect(inferRiskLevel(undefined, ['read'])).toBe('read_only');
  });
});

// ============================================================================
// inferSourceType
// ============================================================================

describe('inferSourceType', () => {
  it('detects builtin', () => {
    expect(inferSourceType('/app/builtin/skills')).toBe('builtin');
  });

  it('detects project', () => {
    expect(inferSourceType('/project/.jarvis/skills')).toBe('project');
  });

  it('detects plugin', () => {
    expect(inferSourceType('/plugins/my-plugin/skills')).toBe('plugin');
  });

  it('defaults to user', () => {
    expect(inferSourceType('/home/user/skills')).toBe('user');
  });
});

// ============================================================================
// SkillRegistry
// ============================================================================

describe('SkillRegistry', () => {
  let registry: SkillRegistry;
  let skillsDir: string;

  beforeEach(() => {
    registry = new SkillRegistry();
    skillsDir = path.join(tmpDir, 'skills');
    fs.mkdirSync(skillsDir, { recursive: true });
  });

  it('discovers skills from a directory', () => {
    createSkillFile(skillsDir, 'SKILL.md', 's1');

    registry.discover({ builtinDir: tmpDir });
    expect(registry.size).toBe(1);
    expect(registry.get('s1')).toBeDefined();
  });

  it('listLoadable excludes quarantined and disabled', () => {
    createSkillFile(skillsDir, 'SKILL.md', 'good');
    createSkillFile(
      path.join(tmpDir, 'bad'),
      'SKILL.md',
      'bad',
      { quarantined: 'true' },
    );

    registry.discover({ builtinDir: tmpDir });
    expect(registry.listLoadable()).toHaveLength(1);
  });

  it('listBySource filters by source', () => {
    createSkillFile(path.join(tmpDir, 'a'), 'SKILL.md', 'builtin-skill');
    createSkillFile(path.join(tmpDir, 'b'), 'SKILL.md', 'user-skill');

    registry.discover({ builtinDir: path.join(tmpDir, 'a'), userDir: path.join(tmpDir, 'b') });

    expect(registry.listBySource('builtin')).toHaveLength(1);
    expect(registry.listBySource('user')).toHaveLength(1);
  });

  it('loadBody strips frontmatter', () => {
    createSkillFile(skillsDir, 'SKILL.md', 'body-test', {}, 'Actual body here.');
    registry.discover({ builtinDir: tmpDir });

    const spec = registry.get('body-test');
    expect(spec).toBeDefined();
    const body = registry.loadBody(spec!);
    expect(body).toBe('Actual body here.');
  });

  it('invalidateCache clears specs', () => {
    createSkillFile(skillsDir, 'SKILL.md', 's1');
    registry.discover({ builtinDir: tmpDir });

    registry.invalidateCache();
    expect(registry.size).toBe(0);
  });

  it('returns undefined for unknown skill', () => {
    expect(registry.get('unknown')).toBeUndefined();
  });

  it('uses extraDirs for plugin-provided skills', () => {
    const pluginDir = path.join(tmpDir, 'plugin-skills');
    fs.mkdirSync(pluginDir, { recursive: true });
    createSkillFile(pluginDir, 'SKILL.md', 'plugin-skill');

    registry.discover({
      extraDirs: [{ path: pluginDir, source: 'plugin' }],
    });

    expect(registry.listBySource('plugin')).toHaveLength(1);
  });
});

// ============================================================================
// SkillMatcher
// ============================================================================

describe('SkillMatcher', () => {
  let matcher: SkillMatcher;

  beforeEach(() => {
    matcher = new SkillMatcher();
  });

  function makeSpec(name: string, description: string, tags?: string[]): SkillSpec {
    return {
      name,
      description,
      path: `/skills/${name}/SKILL.md`,
      source: 'builtin',
      allowedTools: ['read'],
      riskLevel: 'read_only',
      enabled: true,
      quarantined: false,
      trustLevel: 50,
      tags,
    };
  }

  it('matches by tag', () => {
    const skills = [
      makeSpec('git-skill', 'Git operations', ['git', 'version-control']),
    ];

    const matches = matcher.match('Help me with git branching', skills);
    expect(matches).toHaveLength(1);
    expect(matches[0].reason).toContain('tag:git');
    expect(matches[0].score).toBeGreaterThanOrEqual(40);
  });

  it('matches by name keywords', () => {
    const skills = [
      makeSpec('python-debugging', 'Debug Python apps'),
    ];

    const matches = matcher.match('I need help with python', skills);
    expect(matches).toHaveLength(1);
    expect(matches[0].reason).toContain('name');
  });

  it('matches by description keywords', () => {
    const skills = [
      makeSpec('code-formatter', 'Format and lint code automatically'),
    ];

    const matches = matcher.match('I want to format my code', skills);
    expect(matches).toHaveLength(1);
    expect(matches[0].reason).toContain('desc');
  });

  it('scores combined matches higher', () => {
    const skills = [
      makeSpec('typescript-help', 'Help with TypeScript coding', ['typescript']),
    ];

    const matches = matcher.match('Help me write TypeScript code', skills);
    expect(matches).toHaveLength(1);
    // Tag match + name match + desc match
    expect(matches[0].score).toBeGreaterThanOrEqual(60);
  });

  it('returns empty for no matches', () => {
    const skills = [makeSpec('zig-build', 'Zig build system', ['zig'])];
    const matches = matcher.match('Write a rust web server with actix', skills);
    expect(matches).toEqual([]);
  });

  it('sorts by score descending', () => {
    const skills = [
      makeSpec('skill-a', 'A', ['keyword']),
      makeSpec('skill-b', 'B keyword', []),
    ];

    const matches = matcher.match('keyword', skills);
    expect(matches).toHaveLength(2);
    expect(matches[0].skill.name).toBe('skill-a'); // tag match scores higher
  });
});

// ============================================================================
// SkillExecutor
// ============================================================================

describe('SkillExecutor', () => {
  let registry: SkillRegistry;
  let executor: SkillExecutor;
  let skillsDir: string;

  beforeEach(() => {
    registry = new SkillRegistry();
    executor = new SkillExecutor(registry);
    skillsDir = path.join(tmpDir, 'skills');
    fs.mkdirSync(skillsDir, { recursive: true });
  });

  it('matches and assembles instruction block', () => {
    createSkillFile(
      skillsDir,
      'SKILL.md',
      'git-help',
      { tags: 'git' },
      'Use git status, git diff, and git log.',
    );

    registry.discover({ builtinDir: tmpDir });

    const result = executor.execute({
      taskText: 'Help me with git commands',
    });

    expect(result.included).toHaveLength(1);
    expect(result.included[0].name).toBe('git-help');
    expect(result.instructionBlock).toContain('git-help');
    expect(result.instructionBlock).toContain('git status');
  });

  it('respects maxSkills', () => {
    for (let i = 0; i < 5; i++) {
      createSkillFile(
        path.join(tmpDir, `s${i}`),
        'SKILL.md',
        `skill-${i}`,
        { tags: 'common' },
        `Skill ${i} body.`,
      );
    }

    registry.discover({ builtinDir: tmpDir });

    const result = executor.execute({
      taskText: 'common task',
      maxSkills: 2,
    });

    expect(result.included.length).toBeLessThanOrEqual(2);
  });

  it('selectAndExecute applies allowlist/denylist', () => {
    createSkillFile(path.join(tmpDir, 'a'), 'SKILL.md', 'allowed-skill', { tags: 'test' });
    createSkillFile(path.join(tmpDir, 'b'), 'SKILL.md', 'blocked-skill', { tags: 'test' });

    registry.discover({ builtinDir: tmpDir });

    const result = executor.selectAndExecute(
      { taskText: 'test' },
      undefined,
      ['blocked-skill'],
    );

    expect(result.included).toHaveLength(1);
    expect(result.included[0].name).toBe('allowed-skill');
  });

  it('returns empty result when no skills match', () => {
    createSkillFile(skillsDir, 'SKILL.md', 'python-skill', { tags: 'python' });
    registry.discover({ builtinDir: tmpDir });

    const result = executor.execute({ taskText: 'rust programming' });
    expect(result.included).toEqual([]);
    expect(result.instructionBlock).toBe('');
  });

  it('respects maxChars budget', () => {
    const longBody = 'x'.repeat(5000);
    createSkillFile(skillsDir, 'SKILL.md', 'big-skill', { tags: 'test' }, longBody);
    registry.discover({ builtinDir: tmpDir });

    const result = executor.execute({
      taskText: 'test',
      maxChars: 100,
    });

    // Should be empty or very small (< 100 chars)
    expect(result.instructionBlock.length).toBeLessThan(150);
  });
});
