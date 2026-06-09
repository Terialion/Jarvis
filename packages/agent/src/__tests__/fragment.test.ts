import { describe, expect, it } from 'vitest';
import {
  CurrentRequestFragment,
  FragmentRegistry,
  MemoryIndexSummaryFragment,
  ProjectContextFragment,
  SettingsUpdateFragment,
  SkillsIndexFragment,
} from '../fragment.js';
import type { TurnContext } from '../context.js';

function makeTurnContext(overrides: Partial<TurnContext> = {}): TurnContext {
  return {
    userInput: 'current request',
    cwd: '/test',
    modelProvider: null,
    modelName: 'test-model',
    permissionMode: 'workspace_write',
    contextPack: {
      project: {
        cwd: '/test',
        repoRoot: '/test',
        projectName: 'test',
        projectFilesHint: [],
        projectInstructions: 'Use pnpm and keep commits small.',
      },
      conversation: {
        threadId: null,
        turnId: 'turn_1',
        recentMessages: [],
        compactedSummary: null,
      },
      memory: {
        shortTerm: {},
        longTermRefs: [{ key: 'prefers-pnpm', value: 'use pnpm', memory_type: 'user' }],
      },
      skills: {
        availableSkills: [{ name: 'web-search', description: 'Search the web safely.' }],
        loadedSkills: [],
        skillObservations: [],
        researchObservations: [],
        activeTask: null,
      },
      tokenBudget: {},
      warnings: [],
    },
    modelBackend: null,
    projectId: null,
    sessionId: null,
    turnId: null,
    memorySnapshot: '<memory-context>\nSaved user preference\n</memory-context>',
    ...overrides,
  };
}

describe('fragments', () => {
  it('renders current request using clean XML markers', () => {
    const fragment = new CurrentRequestFragment();
    const rendered = fragment.render(makeTurnContext());
    expect(rendered).toContain('<current-request>');
    expect(rendered).toContain('</current-request>');
    expect(rendered).not.toContain('鈹');
  });

  it('renders project, skills, and memory fragments through the registry', () => {
    const ctx = makeTurnContext();
    const registry = new FragmentRegistry();
    registry.register(new ProjectContextFragment());
    registry.register(new SkillsIndexFragment());
    registry.register(new MemoryIndexSummaryFragment());

    const rendered = registry.renderAll(ctx);
    expect(rendered.some((entry) => entry.content.includes('<project-context>'))).toBe(true);
    expect(rendered.some((entry) => entry.content.includes('<skills>'))).toBe(true);
    expect(rendered.some((entry) => entry.content.includes('<available-memory>'))).toBe(true);
    expect(rendered.find((entry) => entry.content.includes('<project-context>'))?.promptPart.bucket).toBe('project');
    expect(rendered.find((entry) => entry.content.includes('<skills>'))?.promptPart.bucket).toBe('skills');
    expect(rendered.find((entry) => entry.content.includes('<available-memory>'))?.promptPart.bucket).toBe('memory');
  });

  it('renders settings update instead of project context when settings changed', () => {
    const ctx = makeTurnContext({
      isFirstTurn: false,
      settingsDiff: {
        permission: '- permission mode changed to plan',
      },
    });

    const settings = new SettingsUpdateFragment().render(ctx);
    expect(settings).toContain('<settings-update>');
    expect(settings).toContain('permission mode changed to plan');
  });
});
