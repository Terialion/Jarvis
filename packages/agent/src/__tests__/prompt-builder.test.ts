import { describe, it, expect } from 'vitest';
import { PromptBuilder } from '../prompt-builder.js';
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

  it('emits tool results with role=tool and tool_call_id', () => {
    const ctx = makeTurnContext({
      contextPack: {
        ...makeTurnContext().contextPack!,
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
});