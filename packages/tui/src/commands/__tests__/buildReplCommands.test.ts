import { describe, expect, it, vi } from 'vitest';
import { buildReplCommands, SLASH_COMMANDS } from '../index.js';

// Minimal mock context
function mockCtx(overrides: Record<string, unknown> = {}) {
  return {
    store: null,
    sid: null,
    skills: null,
    historyRef: { current: [] },
    messages: [],
    setMessages: vi.fn(),
    setIsLoading: vi.fn(),
    cwd: '/tmp',
    modelRef: { current: 'test-model' },
    apiKeyRef: { current: undefined },
    baseURLRef: { current: undefined },
    reasoningEffortRef: { current: 'high' },
    systemPromptRef: { current: undefined },
    modifiedFilesRef: { current: new Set() },
    getAgent: vi.fn(),
    invalidateAgent: vi.fn(),
    maxTurns: 30,
    outputStyleRef: { current: 'default' },
    permissionModeRef: { current: 'workspace_write' },
    mcpClientRef: { current: null },
    mcpStatusesRef: { current: [] },
    mcpConfiguredRef: { current: [] },
    tokenTrackerRef: { current: null },
    toolsRef: { current: null },
    liveContextUsageRef: { current: null },
    ...overrides,
  } as any;
}

describe('SLASH_COMMANDS', () => {
  it('has unique names', () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(new Set(names).size).toBe(names.length);
  });

  it('includes help, clear, model, effort, context', () => {
    const names = SLASH_COMMANDS.map((c) => c.name);
    expect(names).toContain('help');
    expect(names).toContain('clear');
    expect(names).toContain('model');
    expect(names).toContain('effort');
    expect(names).toContain('context');
  });
});

describe('buildReplCommands', () => {
  it('returns commands for all slash commands + skill commands', () => {
    const ctx = mockCtx();
    const cmds = buildReplCommands(ctx, vi.fn());
    // Should have at least as many commands as SLASH_COMMANDS
    expect(cmds.length).toBeGreaterThanOrEqual(SLASH_COMMANDS.length);
    expect(cmds.map((c) => c.name)).toContain('help');
    expect(cmds.map((c) => c.name)).toContain('clear');
  });

  it('/help opens popup when setHelpPopupOpen is provided', () => {
    const ctx = mockCtx();
    const setHelpPopupOpen = vi.fn();
    const cmds = buildReplCommands(ctx, vi.fn(), null, undefined, undefined, setHelpPopupOpen);
    const helpCmd = cmds.find((c) => c.name === 'help')!;
    helpCmd.onExecute('', '/help');
    expect(setHelpPopupOpen).toHaveBeenCalledWith(true);
  });

  it('/help falls back to text when setHelpPopupOpen is not provided', () => {
    const ctx = mockCtx();
    const setMessages = vi.fn();
    const cmds = buildReplCommands(ctx, setMessages);
    const helpCmd = cmds.find((c) => c.name === 'help')!;
    helpCmd.onExecute('', '/help');
    expect(setMessages).toHaveBeenCalled();
  });

  it('/model opens selector when no args and setModelSelectorOpen is provided', () => {
    const ctx = mockCtx();
    const setModelSelectorOpen = vi.fn();
    const cmds = buildReplCommands(ctx, vi.fn(), null, setModelSelectorOpen);
    const modelCmd = cmds.find((c) => c.name === 'model')!;
    modelCmd.onExecute('', '/model');
    expect(setModelSelectorOpen).toHaveBeenCalledWith(true);
  });

  it('/effort opens selector when no args and setEffortSelectorOpen is provided', () => {
    const ctx = mockCtx();
    const setEffortSelectorOpen = vi.fn();
    const cmds = buildReplCommands(ctx, vi.fn(), null, undefined, setEffortSelectorOpen);
    const effortCmd = cmds.find((c) => c.name === 'effort')!;
    effortCmd.onExecute('', '/effort');
    expect(setEffortSelectorOpen).toHaveBeenCalledWith(true);
  });

  it('non-overridden command calls setMessages', () => {
    const ctx = mockCtx();
    const setMessages = vi.fn();
    const cmds = buildReplCommands(ctx, setMessages);
    // /skills is a non-overridden command
    const skillsCmd = cmds.find((c) => c.name === 'skills');
    if (skillsCmd) {
      skillsCmd.onExecute('', '/skills');
      expect(setMessages).toHaveBeenCalled();
    }
  });
});
