import { describe, it, expect } from 'vitest';
import {
  PromptBuilder,
  SYSTEM_PROMPT_DYNAMIC_BOUNDARY,
  buildSystemPrompt,
  buildSystemPromptResult,
} from '../prompt-builder.js';
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
        projectInstructions: null,
      },
      conversation: {
        threadId: null,
        turnId: 'turn_1',
        recentMessages: [],
        compactedSummary: null,
      },
      memory: { shortTerm: {}, longTermRefs: [] },
      skills: {
        availableSkills: [],
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
    ...overrides,
  };
}

describe('PromptBuilder', () => {
  const builder = new PromptBuilder();

  it('builds stable and dynamic system prompt sections with a boundary marker', () => {
    const result = buildSystemPromptResult({
      modelName: 'test-model',
      mode: 'full',
      permissionMode: 'workspace_write',
    });

    expect(result.stableSections.length).toBeGreaterThan(0);
    expect(result.dynamicSections.length).toBeGreaterThan(0);
    expect(result.prompt).toContain(SYSTEM_PROMPT_DYNAMIC_BOUNDARY);

    const stableIds = result.stableSections.map((section) => section.id);
    const dynamicIds = result.dynamicSections.map((section) => section.id);
    expect(stableIds).toContain('identity');
    expect(stableIds).toContain('tool-policy');
    expect(dynamicIds).toContain('mode');
    expect(dynamicIds).toContain('environment');
  });

  it('changes only the mode-specific section when permission mode changes', () => {
    const workspaceWrite = buildSystemPromptResult({
      modelName: 'test-model',
      mode: 'full',
      permissionMode: 'workspace_write',
    });
    const planMode = buildSystemPromptResult({
      modelName: 'test-model',
      mode: 'full',
      permissionMode: 'plan',
    });

    expect(workspaceWrite.stableSections).toEqual(planMode.stableSections);

    const workspaceMode = workspaceWrite.dynamicSections.find((section) => section.id === 'mode');
    const planModeSection = planMode.dynamicSections.find((section) => section.id === 'mode');
    expect(workspaceMode?.content).not.toEqual(planModeSection?.content);
    expect(planModeSection?.content).toContain('plan');
  });

  it('emits prompts without known mojibake markers', () => {
    const prompt = buildSystemPrompt('test-model', 'full');
    expect(prompt).not.toContain('鈥');
    expect(prompt).not.toContain('涓');
    expect(prompt).not.toContain('鎴');
  });

  it('emits tool results with role=tool and tool_call_id', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        project: {
          ...makeTurnContext().contextPack!.project,
          projectInstructions: 'Use pnpm and keep commits small.',
        },
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'read foo.ts' },
            { role: 'assistant', content: 'Reading...' },
            {
              role: 'tool',
              content: 'export const x = 1;',
              tool_call_id: 'call_abc',
              metadata: { tool_name: 'read' },
            },
          ],
          compactedSummary: null,
        },
      },
    });

    const messages = builder.buildMessages(ctx);

    // Find the tool message
    const toolMsgs = messages.filter((m) => m.role === 'tool');
    expect(toolMsgs.length).toBe(1);
    expect(toolMsgs[0].tool_call_id).toBe('call_abc');
    expect(toolMsgs[0].content).toContain('read');
    expect(toolMsgs[0].content).toContain('export const x = 1;');
    expect(toolMsgs[0].promptPart?.category).toBe('history');
  });

  it('preserves user and assistant roles natively', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'hello' },
            { role: 'assistant', content: 'hi there' },
            { role: 'user', content: 'how are you' },
            { role: 'assistant', content: 'doing well' },
          ],
          compactedSummary: null,
        },
      },
    });

    const messages = builder.buildMessages(ctx);

    const roles = messages.map((m) => m.role);
    // system -> (skills maybe) -> system (history banner) -> user -> assistant -> user -> assistant -> user (current)
    expect(roles.filter((r) => r === 'user').length).toBe(3); // 2 history + 1 current
    expect(roles.filter((r) => r === 'assistant').length).toBe(2);
    expect(messages.some((message) => message.promptPart?.category === 'history')).toBe(true);
  });

  it('does not include tool_call_id on non-tool messages', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'hello' },
            { role: 'assistant', content: 'hi' },
          ],
          compactedSummary: null,
        },
      },
    });

    const messages = builder.buildMessages(ctx);
    for (const m of messages) {
      if (m.role !== 'tool') {
        expect(m.tool_call_id).toBeUndefined();
      }
    }
  });

  it('handles empty history gracefully', () => {
    const ctx = makeTurnContext();

    const messages = builder.buildMessages(ctx);
    expect(messages.length).toBeGreaterThan(0);
    expect(messages[messages.length - 1].role).toBe('user');
    expect(messages[messages.length - 1].content).toContain('current request');
  });

  it('injects compaction summary when present', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [],
          compactedSummary: 'User asked to refactor auth, decided to use JWT.',
        },
      },
    });

    const messages = builder.buildMessages(ctx);
    const summaryMsg = messages.find((m) => m.content.includes('conversation-summary'));
    expect(summaryMsg).toBeDefined();
    expect(summaryMsg!.content).toContain('JWT');
  });

  it('injects full project context only on first turn', () => {
    const firstTurn = makeTurnContext({
      isFirstTurn: true,
      contextPack: {
        ...makeTurnContext().contextPack!,
        project: {
          ...makeTurnContext().contextPack!.project,
          projectInstructions: 'Use pnpm and keep commits small.',
        },
      },
    });

    const messages = builder.buildMessages(firstTurn);
    expect(messages.some((message) => message.content.includes('<project-context>'))).toBe(true);
    expect(messages.some((message) => message.content.includes('<settings-update>'))).toBe(false);
    expect(messages.find((message) => message.content.includes('<project-context>'))?.promptPart?.bucket).toBe('project');
  });

  it('injects settings diff instead of full project context on steady-state turns', () => {
    const steadyState = makeTurnContext({
      isFirstTurn: false,
      settingsDiff: {
        permission: '- permission mode changed to plan',
      },
      contextPack: {
        ...makeTurnContext().contextPack!,
        project: {
          ...makeTurnContext().contextPack!.project,
          projectInstructions: 'Use pnpm and keep commits small.',
        },
      },
    });

    const messages = builder.buildMessages(steadyState);
    expect(messages.some((message) => message.content.includes('<settings-update>'))).toBe(true);
    expect(messages.some((message) => message.content.includes('<project-context>'))).toBe(false);
    expect(messages.find((message) => message.content.includes('<settings-update>'))?.promptPart?.bucket).toBe('settings');
  });

  it('builds typed prompt parts before projecting to provider messages', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
        project: {
          ...makeTurnContext().contextPack!.project,
          projectInstructions: 'Use pnpm and keep commits small.',
        },
        conversation: {
          threadId: null,
          turnId: 'turn_1',
          recentMessages: [
            { role: 'user', content: 'older request' },
            { role: 'assistant', content: 'older answer' },
            {
              role: 'tool',
              content: 'tool output',
              tool_call_id: 'call_hist_1',
              metadata: { tool_name: 'read' },
            },
          ],
          compactedSummary: 'Earlier summary',
        },
      },
    });

    const parts = builder.buildParts(ctx);
    expect(parts[0].promptPart.bucket).toBe('system');
    expect(parts.some((part) => part.promptPart.bucket === 'project')).toBe(true);
    expect(parts.some((part) => part.promptPart.bucket === 'summary')).toBe(true);
    expect(parts.some((part) => part.promptPart.id === 'conversation_history')).toBe(true);
    expect(parts.some((part) => part.promptPart.id.startsWith('history_tool_'))).toBe(true);
    expect(parts[parts.length - 1].promptPart.bucket).toBe('intent');
  });
});
