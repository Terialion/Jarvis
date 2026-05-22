import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { SkillRegistry, SkillExecutor, SkillLoader } from '@jarvis/skills';
import type { SkillSource } from '@jarvis/skills';
import * as fs from 'node:fs';
import * as path from 'node:path';
import * as os from 'node:os';

describe('E2E: Skills', () => {
  const tmpDir = path.join(os.tmpdir(), `jarvis-e2e-skills-${Date.now()}`);

  beforeAll(() => {
    fs.mkdirSync(tmpDir, { recursive: true });
  });

  afterAll(() => {
    if (fs.existsSync(tmpDir)) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    }
  });

  it('SkillLoader: parses a SKILL.md file', () => {
    const loader = new SkillLoader();
    const skillDir = path.join(tmpDir, 'my-skill');
    fs.mkdirSync(skillDir, { recursive: true });

    const skillMd = `---
name: test-skill
description: A test skill for E2E testing
tags: test, e2e
risk_level: read_only
enabled: true
---

# Test Skill

This is a test skill.
`;
    fs.writeFileSync(path.join(skillDir, 'SKILL.md'), skillMd);

    const spec = loader.parseSkillFile(path.join(skillDir, 'SKILL.md'), 'project' as SkillSource);
    expect(spec).not.toBeNull();
    expect(spec!.name).toBe('test-skill');
    expect(spec!.description).toBe('A test skill for E2E testing');
    expect(spec!.tags).toContain('test');
    expect(spec!.tags).toContain('e2e');
    expect(spec!.riskLevel).toBe('read_only');
  });

  it('SkillRegistry: discovers skills from directory', () => {
    const registry = new SkillRegistry();

    const skillDir1 = path.join(tmpDir, 'skill-a');
    fs.mkdirSync(skillDir1, { recursive: true });
    fs.writeFileSync(path.join(skillDir1, 'SKILL.md'), `---
name: skill-alpha
description: First test skill
tags: alpha
---

# Skill Alpha
`);

    const skillDir2 = path.join(tmpDir, 'skill-b');
    fs.mkdirSync(skillDir2, { recursive: true });
    fs.writeFileSync(path.join(skillDir2, 'SKILL.md'), `---
name: skill-beta
description: Second test skill
tags: beta
---

# Skill Beta
`);

    const skills = registry.discover({ projectDir: tmpDir });
    // Should find at least the 2 we just created
    expect(skills.length).toBeGreaterThanOrEqual(2);
    const names = skills.map((s) => s.name).sort();
    expect(names).toContain('skill-alpha');
    expect(names).toContain('skill-beta');
  });

  it('SkillExecutor: matches and assembles instruction block', () => {
    const registry = new SkillRegistry();

    const skillDir = path.join(tmpDir, 'matched-skill');
    fs.mkdirSync(skillDir, { recursive: true });
    fs.writeFileSync(path.join(skillDir, 'SKILL.md'), `---
name: deploy-skill
description: Handles deployment tasks
tags: deploy, production
risk_level: command
allowed_tools: bash, read, write
---

# Deploy Skill

## Instructions
When the user wants to deploy, use these steps:
1. Run tests
2. Build
3. Push
`);
    registry.discover({ projectDir: tmpDir });
    const executor = new SkillExecutor(registry);

    // Match with a deploy-related query
    const result = executor.execute({
      taskText: 'Can you deploy this to production?',
      maxSkills: 3,
    });

    expect(result.included.length).toBeGreaterThanOrEqual(1);
    expect(result.included[0].name).toBe('deploy-skill');
    expect(result.instructionBlock.length).toBeGreaterThan(0);
    expect(result.instructionBlock).toContain('Run tests');
  });

  it('SkillExecutor: returns empty for irrelevant queries', () => {
    const registry = new SkillRegistry();

    const skillDir = path.join(tmpDir, 'deploy-only');
    fs.mkdirSync(skillDir, { recursive: true });
    fs.writeFileSync(path.join(skillDir, 'SKILL.md'), `---
name: deploy-only-skill
description: Deployment only
tags: deploy, ops
---

# Deploy Only
`);
    registry.discover({ projectDir: tmpDir });
    const executor = new SkillExecutor(registry);

    const result = executor.execute({
      taskText: 'Write a simple hello world function',
      maxSkills: 3,
    });

    // deploy skill shouldn't match a coding request
    expect(result.included.length).toBe(0);
  });
});
