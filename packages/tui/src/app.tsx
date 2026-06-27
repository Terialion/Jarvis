import type React from 'react';
import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { readFileSync, existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { scanFiles, type FileEntry } from './vendor/ui/utils/fileScanner.js';
import { REPL } from './vendor/ui/REPL.js';
import type { StatusDetailLine } from './vendor/ui/REPL.js';
import type { Message, MessageContent } from './vendor/ui/MessageList.js';
import type { StatusLineSegment } from './vendor/ui/StatusLine.js';
import { WelcomeScreen } from './vendor/ui/WelcomeScreen.js';
import { loadSettings, saveSettings, type UserSettings } from './settings-store.js';
import { AgentLoop, AgentEventBus, AgentMailbox, TokenTracker, estimateTokens, validateContextWindow, resolveContextWindow, getAllModels, parseModelName, findModel, buildSystemPrompt, createMemorySearchHandler, createMemoryGetHandler, createMemoryWriteHandler, createMemoryDeleteHandler, type ThreadEvent, type ModelInfo } from '@jarvis/agent';
import {
  ToolRegistry,
  allBuiltinTools,
  createToolRuntime,
  setAskUserQuestionBridge,
  setPlanReviewBridge,
  createSkillLoadTool,
  createSkillTool,
  createAgentTool,
  createListMcpResourcesTool,
  createReadMcpResourceTool,
  createMcpStatusTool,
  createMcpHealthcheckTool,
  createMcpToolEntries,
  webSearchTool,
  webFetchTool,
  createTavilySearchTool,
  createTavilyFetchTool,
  tryCreateTavilySearch,
  tryCreateTavilyFetch,
  applyToolLifecycleEvent,
  buildToolLifecycleSummary,
  createToolLifecycleState,
  PermissionStateMachine,
  type ToolRuntimeLifecycleEvent,
} from '@jarvis/tools';
import type { AskQuestionDef, PlanReviewRequest, PermissionState } from '@jarvis/tools';
import type { PlanReviewDecision } from './vendor/ui/PlanReview';
import { SkillRegistry, SkillExecutor } from '@jarvis/skills';
import { SessionStore, MarkdownMemoryStore } from '@jarvis/store';
import { SubagentPool, SubagentRunner } from '@jarvis/subagents';
import { MCPClient, type McpConnectionStatus, type McpServerConfig } from '@jarvis/mcp';
import { HookRegistry } from '@jarvis/hooks';
import { buildInlinePlanReviewText, ConfigWatcher, JARVIS_REASONING_EFFORTS, type JarvisReasoningEffort } from '@jarvis/shared';
import { LLMProvider } from '@jarvis/agent';
import type { ModelReasoningEffort } from '@jarvis/agent';
import type { TUIOptions, TUIDebugEvent } from './types.js';
import type { ChatMessage } from '@jarvis/shared';
import { formatToolLine } from './vendor/ui/tool-display.js';
import { buildContextBreakdownSegments, buildStatusSegments } from './status-segments.js';
import type { CodexTaskSnapshot, CodexTurnSnapshot } from './presentation/codex-timeline-state.js';
// Extracted modules
import { buildReplCommands, resolveSlashCommand, SLASH_COMMANDS, makeSysMsg, type SlashCommandCtx, type REPLCommandDef, type LiveContextUsage } from './commands/index.js';
import { getGitBranch, discoverPluginSkillDirs, discoverPluginMcpServers, discoverUserMcpServers, discoverProjectMcpServers } from './utils/discovery.js';
import { buildContextPanelLines, resolveContextMode, type SkillTokenEntry, type ToolTokenEntry } from './context-panel.js';
import { formatMcpDiagnostics, refreshMcpStatuses } from './utils/mcp-diagnostics.js';
import { extractModifiedFiles, safeJsonParse, computeFileChange, formatFileChangeSummary, FILE_MODIFYING_TOOLS, parseToolContent, type FileChange } from './utils/tool-formatters.js';
import { estimateTokensFromText, estimateMemoryEntries, buildContextProgressBar, estimateTurnTokenCount, buildMcpFooterLines } from './utils/token-estimation.js';
import { decodeHtmlEntities } from './vendor/ui/utils/markdown.js';
import { TuiStreamAssembler } from './vendor/shared/stream-assembler.js';
import {
  resolveContentTokenStreamStart,
  resolveToolBoundaryStreamTransition,
} from './stream-run-policy.js';
import { loadJarvisConfig } from '@jarvis/shared';
import { resolveModelCredentials } from './utils/credentials.js';
import { connectMcpServers } from '@jarvis/mcp';
import { getCronScheduler } from '@jarvis/tools';
import { humanizeToolName, summarizeAgentEventProgress } from './progress-summary.js';
import { sanitizeReasoningForDisplay } from './reasoning-quality.js';

function formatInlinePlanReview(plan: PlanReviewRequest): string {
  const lines = [
    `Updated plan: ${plan.summary}`,
    '',
    ...plan.steps.map((step, index) => {
      const details = [
        step.files?.length ? `[${step.files.join(', ')}]` : '',
        step.verification ? `verify: ${step.verification}` : '',
      ]
        .filter(Boolean)
        .join(' · ');
      return `${index + 1}. ${step.step}${details ? ` · ${details}` : ''}`;
    }),
  ];

  if (plan.allowedPrompts?.length) {
    lines.push('', 'Required permissions:');
    for (const prompt of plan.allowedPrompts) {
      lines.push(`- ${prompt.tool}: ${prompt.prompt}`);
    }
  }

  lines.push(
    '',
    'Tell me what to change if this plan needs edits.',
    'Otherwise use Enter to proceed or Esc to cancel.',
  );

  return lines.join('\n');
}

function createUiMessageId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID()}`;
}

export function App({ options }: { options: TUIOptions }): React.ReactNode {
  const [messages, setMessages] = useState<Message[]>([]);
  const [threadEvents, setThreadEvents] = useState<ThreadEvent[]>([]);
  const [codexTaskSnapshots, setCodexTaskSnapshots] = useState<CodexTaskSnapshot[]>([]);
  const [codexTurnSnapshots, setCodexTurnSnapshots] = useState<CodexTurnSnapshot[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const agentRef = useRef<AgentLoop | null>(null);
  const historyRef = useRef<ChatMessage[]>([]);
  const toolsRef = useRef<ToolRegistry | null>(null);
  const skillsRef = useRef<SkillRegistry | null>(null);
  const executorRef = useRef<SkillExecutor | null>(null);
  const sessionStoreRef = useRef<SessionStore | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const sessionReadyRef = useRef(false);
  const savedSettings = loadSettings();
  const modelRef = useRef<string>(savedSettings.active_model || savedSettings.model || options.model);
  const apiKeyRef = useRef<string | undefined>(options.apiKey);
  const baseURLRef = useRef<string | undefined>(options.baseURL);

  // Resolve provider credentials for the initial model
  // This ensures the correct API key and base URL are used based on the model's provider
  const initialCreds = resolveModelCredentials(modelRef.current);
  if (!apiKeyRef.current) apiKeyRef.current = initialCreds.apiKey;
  if (!baseURLRef.current) baseURLRef.current = initialCreds.baseURL;
  const reasoningEffortRef = useRef<string>(savedSettings.reasoning_effort || options.reasoningEffort || 'high');
  const systemPromptRef = useRef<string | undefined>(options.systemPrompt);
  const modifiedFilesRef = useRef<Set<string>>(new Set());
  const outputStyleRef = useRef<string>(savedSettings.output_style || 'default');
  const permissionModeRef = useRef<string>(savedSettings.permission_mode || 'workspace_write');
  const poolRef = useRef<SubagentPool | null>(null);
  const mailboxRef = useRef<AgentMailbox>(new AgentMailbox());
  const mcpRef = useRef<MCPClient | null>(null);
  const mcpStatusesRef = useRef<McpConnectionStatus[]>([]);
  const mcpConfiguredRef = useRef<Array<{ id: string; plugin?: string; config: McpServerConfig }>>([]);
  const tokenTrackerRef = useRef<TokenTracker | null>(null);
  const liveContextUsageRef = useRef<LiveContextUsage | null>(null);
  const elapsedRef = useRef<number>(0);
  const elapsedTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const taskCountRef = useRef<{ pending: number; in_progress: number; completed: number }>({ pending: 0, in_progress: 0, completed: 0 });
  const abortRef = useRef<AbortController | null>(null);
  const permManagerRef = useRef<import('@jarvis/tools').PermissionManager | null>(null);
  const stateMachineRef = useRef<PermissionStateMachine | null>(null);
  const [permissionState, setPermissionState] = useState<PermissionState>('idle');
  const [modeVersion, setModeVersion] = useState(0);
  const [modelVersion, setModelVersion] = useState(0);

  // Model selector state
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false);

  // Effort selector state
  const [effortSelectorOpen, setEffortSelectorOpen] = useState(false);

  // Help popup state
  const [helpPopupOpen, setHelpPopupOpen] = useState(false);
  const [contextPanel, setContextPanel] = useState<{ title: string; subtitle?: string; lines: string[] } | null>(null);
  const [mcpPanel, setMcpPanel] = useState<{ title: string; subtitle?: string; lines: string[] } | null>(null);

  // Persistent command history — survives restarts like CC/Codex
  const HISTORY_FILE = join(process.cwd(), '.jarvis', 'history.json');
  const historyRef2 = useRef<string[]>([]);
  if (historyRef2.current.length === 0 && existsSync(HISTORY_FILE)) {
    try {
      const data = JSON.parse(readFileSync(HISTORY_FILE, 'utf-8'));
      if (Array.isArray(data)) historyRef2.current = data.slice(0, 500);
    } catch { /* corrupt file, start fresh */ }
  }
  const compactedCountRef = useRef(0);
  const peakContextRef = useRef(0);
  const [compactedVersion, setCompactedVersion] = useState(0);
  const [historyVersion, setHistoryVersion] = useState(0);
  const handleHistoryAdd = useCallback((entry: string) => {
    // Dedup consecutive duplicates
    if (historyRef2.current[0] === entry) return;
    historyRef2.current = [entry, ...historyRef2.current].slice(0, 500);
    setHistoryVersion((v) => v + 1);
    try {
      mkdirSync(join(process.cwd(), '.jarvis'), { recursive: true });
      writeFileSync(HISTORY_FILE, JSON.stringify(historyRef2.current, null, 2), 'utf-8');
    } catch { /* best-effort */ }
  }, []);

  // AskUserQuestion bridge state
  const [askQuestions, setAskQuestions] = useState<AskQuestionDef[] | null>(null);
  const askResolveRef = useRef<((answers: Record<string, string>) => void) | null>(null);
  const askRejectRef = useRef<((err: Error) => void) | null>(null);
  // Plan review bridge state (CC-style interactive plan approval)
  const [planReview, setPlanReview] = useState<PlanReviewRequest | null>(null);
  const [planReviewIndex, setPlanReviewIndex] = useState(0);
  const planReviewResolveRef = useRef<((choice: PlanReviewDecision) => void) | null>(null);
  const [streamingContent, setStreamingContent] = useState<string | null>(null);
  const [streamingThinking, setStreamingThinking] = useState<string | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [spinnerVerb, setSpinnerVerb] = useState<string | undefined>(undefined);
  const [spinnerStatus, setSpinnerStatus] = useState<string | undefined>(undefined);
  const [spinnerDetails, setSpinnerDetails] = useState<string[]>([]);
  const [spinnerCompleted, setSpinnerCompleted] = useState<string[]>([]);
  const [spinnerRunning, setSpinnerRunning] = useState<string | undefined>(undefined);
  const [contextUsageVersion, setContextUsageVersion] = useState(0);
  const [mcpStatusVersion, setMcpStatusVersion] = useState(0);
  const [agentEntries, setAgentEntries] = useState<import('./vendor/ui/AgentsPanel.js').AgentStatusEntry[]>([]);

  // @ file reference state
  const [fileEntries, setFileEntries] = useState<FileEntry[]>([]);
  const fileSearchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const handleFileSearch = useCallback((query: string) => {
    // Debounce file scanning to avoid excessive filesystem reads
    if (fileSearchTimerRef.current) clearTimeout(fileSearchTimerRef.current);
    fileSearchTimerRef.current = setTimeout(async () => {
      try {
        const entries = await scanFiles(process.cwd(), query);
        setFileEntries(entries);
      } catch {
        setFileEntries([]);
      }
    }, 150);
  }, []);

  const cwd = process.cwd();
  const gitBranch = useMemo(() => getGitBranch(cwd), [cwd, messages.length]);

  // Subscribe to agent store
  useEffect(() => {
    let unsub: (() => void) | undefined;
    import('./agent-store.js').then(({ agentStore }) => {
      unsub = agentStore.subscribe(() => {
        setAgentEntries(agentStore.getSnapshot());
      });
    });
    return () => { unsub?.(); };
  }, []);
  const streamFlushRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const streamAccumRef = useRef<string>(''); // full accumulated content (OpenClaw replacement mode)
  const streamAssemblerRef = useRef(new TuiStreamAssembler());
  const streamingRunIdRef = useRef<string | null>(null);
  const pendingAssistantResumeRef = useRef<"assistant_resume" | null>(null);
  const streamingSourceTextRef = useRef<string>('');
  const reasoningBufferRef = useRef<string>('');
  const reasoningFlushedRef = useRef(false);
  const reasoningDisplayThrottle = useRef<number>(0);
  const streamingContentRef = useRef<string | null>(null);
  const threadEventsRef = useRef<ThreadEvent[]>([]);
  const eventBusRef = useRef<AgentEventBus | null>(null);
  const toolLifecycleStateRef = useRef(createToolLifecycleState());
  const runStatsRef = useRef<{
    prompt: string;
    startedAt: number;
    trackerStartBlended: number;
    tokenEvents: number;
    tokenChars: number;
    reasoningEvents: number;
    reasoningChars: number;
    toolStarts: number;
    toolEnds: number;
    hadStreamingContent: boolean;
    hadStreamingThinking: boolean;
  } | null>(null);
  const emitDebugEvent = useCallback((event: TUIDebugEvent) => {
    options.debugHooks?.onEvent?.(event);
  }, [options.debugHooks]);
  const updateToolMessageLifecycle = useCallback((
    callId: string,
    patch: {
      status?: 'running' | 'success' | 'error';
      result?: string;
      durationMs?: number;
    },
  ) => {
    setMessages((prev) => prev.map((message) => {
      if (message.id !== `tool_${callId}`) {
        return message;
      }

      const content = [...(message.content as MessageContent[])];
      const toolBlock = content.find((entry) => entry.type === 'tool_use');
      if (!toolBlock || !('status' in toolBlock)) {
        return message;
      }

      const updated = {
        ...toolBlock,
        ...(patch.status ? { status: patch.status } : {}),
        ...(patch.result !== undefined ? { result: patch.result } : {}),
        ...(patch.durationMs !== undefined ? { durationMs: patch.durationMs } : {}),
      };

      return {
        ...message,
        content: content.map((entry) => (entry.type === 'tool_use' ? updated : entry)),
      };
    }));
  }, []);
  const handleToolRuntimeLifecycle = useCallback((event: ToolRuntimeLifecycleEvent) => {
    emitDebugEvent({
      type: 'tool_runtime_state',
      stage: event.stage,
      toolName: event.toolName,
      callId: event.callId,
      argsKey: 'argsKey' in event ? event.argsKey : undefined,
      risk: 'risk' in event ? event.risk : undefined,
      ok: 'ok' in event ? event.ok : undefined,
      reason: 'reason' in event ? event.reason : undefined,
      durationMs: 'durationMs' in event ? event.durationMs : undefined,
      timestamp: Date.now(),
    });
    toolLifecycleStateRef.current = applyToolLifecycleEvent(toolLifecycleStateRef.current, event);
    const summary = buildToolLifecycleSummary(toolLifecycleStateRef.current);
    setSpinnerStatus(summary.statusLine);
    setSpinnerRunning(summary.runningLine);
    setSpinnerCompleted(summary.completedLines);
    if (event.stage === 'dispatch_completed') {
      updateToolMessageLifecycle(event.callId, {
        status: event.ok ? 'success' : 'error',
        durationMs: event.durationMs,
      });
    } else if (event.stage === 'dispatch_failed' || event.stage === 'approval_denied') {
      updateToolMessageLifecycle(event.callId, {
        status: 'error',
        result: 'reason' in event && event.reason ? event.reason : undefined,
        durationMs: 'durationMs' in event ? event.durationMs : undefined,
      });
    }
  }, [emitDebugEvent, updateToolMessageLifecycle]);
  const invalidateAgent = useCallback(() => {
    agentRef.current = null;
    tokenTrackerRef.current = null;
    liveContextUsageRef.current = null;
    poolRef.current = null;
    eventBusRef.current = null;
    compactedCountRef.current = 0;
    peakContextRef.current = 0;
    setCompactedVersion((v) => v + 1);
  }, []);

  // Model selector handlers
  const handleModelSelect = useCallback((result: import('./vendor/ui/ModelSelector.js').ModelSelectionResult) => {
    const { model, mode } = result;
    modelRef.current = model;
    if (mode === 'default') {
      saveSettings({ model, active_model: model });
    }

    // Resolve provider credentials for the new model
    const creds = resolveModelCredentials(model);
    apiKeyRef.current = creds.apiKey;
    baseURLRef.current = creds.baseURL;

    const providerName = findModel(model)?.provider;

    invalidateAgent();
    setModelSelectorOpen(false);
    setModelVersion((v) => v + 1); // Trigger status bar update
    setMessages((prev) => [
      ...prev,
      makeSysMsg(`Model set to: ${model} (provider: ${providerName ?? 'default'})${mode === 'session' ? ' (this session only)' : ''}`),
    ]);
  }, [invalidateAgent, setMessages]);

  const handleModelSelectorCancel = useCallback(() => {
    setModelSelectorOpen(false);
  }, []);

  const handleModelEffortChange = useCallback((effort: string) => {
    reasoningEffortRef.current = effort;
    saveSettings({ reasoning_effort: effort as JarvisReasoningEffort });
    invalidateAgent();
  }, [invalidateAgent]);

  // Effort selector handlers
  const handleEffortSelect = useCallback((effort: string) => {
    reasoningEffortRef.current = effort;
    saveSettings({ reasoning_effort: effort as JarvisReasoningEffort });
    invalidateAgent();
    setEffortSelectorOpen(false);
    setMessages((prev) => [...prev, makeSysMsg(`Reasoning effort set to: ${effort}`)]);
  }, [invalidateAgent, setMessages]);

  const handleEffortSelectorCancel = useCallback(() => {
    setEffortSelectorOpen(false);
  }, []);

  const openContextPanel = useCallback((args: string[]) => {
    const msgCount = historyRef.current.length;
    const messageTokens = Math.ceil(historyRef.current.reduce((sum, m) => sum + m.content.length, 0) / 4);
    const snapshot = tokenTrackerRef.current?.snapshot();
    const live = liveContextUsageRef.current;
    const contextWindow = live?.contextWindow ?? snapshot?.contextWindow ?? 200_000;
    const shortSid = (sessionIdRef.current ?? 'none').slice(-16);
    const modelName = parseModelName(modelRef.current).cleanName;
    const defaultSystemPrompt = buildSystemPrompt(modelName);
    const systemPromptText = systemPromptRef.current?.trim()
      ? `${defaultSystemPrompt}\n\n${systemPromptRef.current}`
      : defaultSystemPrompt;
    const systemPromptTokens = estimateTokensFromText(systemPromptText);
    const memoryEntries = estimateMemoryEntries(cwd);
    const skillEntries: SkillTokenEntry[] = (skillsRef.current?.listLoadable() ?? []).map((skill) => ({
      name: skill.name,
      source: skill.source,
      tokens: estimateTokensFromText(`${skill.name}\n${skill.description}`),
    }));
    const allToolSchemas = toolsRef.current?.getDefinitions() ?? [];
    const toolEntries: ToolTokenEntry[] = allToolSchemas.map((schema) => {
      const fn = (schema as { function?: { name?: string } }).function?.name ?? 'unknown';
      const serialized = JSON.stringify(schema);
      return { name: fn, tokens: estimateTokensFromText(serialized), isMcp: typeof fn === 'string' && fn.toLowerCase().includes('mcp') };
    });
    const memoryTokens = memoryEntries.reduce((acc, item) => acc + item.tokens, 0);
    const skillTokens = skillEntries.reduce((acc, item) => acc + item.tokens, 0);
    const toolTokens = toolEntries.reduce((acc, item) => acc + item.tokens, 0);
    const estimatedTotalTokens = live?.estimatedTotalTokens ?? (systemPromptTokens + toolTokens + memoryTokens + skillTokens + messageTokens);
    const resolvedSystemPromptTokens = live?.systemPromptTokens ?? systemPromptTokens;
    const resolvedMessageTokens = live?.conversationTokens ?? messageTokens;
    const mode = resolveContextMode(args);
    const lines = buildContextPanelLines({
      mode,
      modelName,
      sessionId: shortSid,
      messageCount: msgCount,
      uiMessageCount: messages.length,
      contextWindow,
      estimatedTotalTokens,
      providerReportedTokens: live?.usedTokens ?? snapshot?.totalTokens,
      systemPromptTokens: resolvedSystemPromptTokens,
      messageTokens: resolvedMessageTokens,
      projectContextTokens: live?.projectContextTokens,
      systemToolsTokens: live?.toolSchemasTokens,
      mcpToolsTokens: live?.mcpToolsTokens,
      memoryTokens: live?.memoryTokens,
      skillsTokens: live?.skillsTokens,
      conversationTokens: live?.conversationTokens,
      memoryEntries,
      skillEntries,
      toolEntries,
      mcpConfigured: mcpConfiguredRef.current.map((e) => ({ id: e.id, plugin: e.plugin, command: e.config.command })),
      mcpStatuses: mcpStatusesRef.current.map((s) => ({ id: s.id, state: s.state, serverName: s.serverName, toolCount: s.toolCount, resourceCount: s.resourceCount, error: s.error })),
    });
    setHelpPopupOpen(false);
    setMcpPanel(null);
    setContextPanel({
      title: mode === 'overview' ? 'Context Usage' : `Context Usage · ${mode}`,
      subtitle: `${modelName} · session ${shortSid}`,
      lines,
    });
  }, [cwd, messages.length]);

  const openMcpPanel = useCallback(async (args: string[]) => {
    const mode = (args[0] ?? '').toLowerCase();
    let statuses = mcpStatusesRef.current;
    if (statuses.length === 0 || statuses.every((s) => s.state === 'connecting' || s.state === 'retrying')) {
      statuses = await refreshMcpStatuses({
        mcpClientRef: mcpRef,
        mcpConfiguredRef,
        mcpStatusesRef,
      });
      setMcpStatusVersion((v) => v + 1);
    }
    const configured = mcpConfiguredRef.current;
    const totalCount = statuses.length;
    const readyCount = statuses.filter((s) => s.state === 'ready' || s.state === 'degraded').length;
    const firstError = statuses.find((s) => s.error)?.error;
    const lines = mode === 'full'
      ? formatMcpDiagnostics(configured, statuses, mcpRef.current).split('\n')
      : [
          configured.length === 0
            ? 'No MCP servers configured. Run mcp_bootstrap to add one, then restart Jarvis.'
            : `Pinned MCP summary under status line (${readyCount}/${totalCount} ready).`,
          ...(firstError ? ['', `First error: ${firstError}`] : []),
          '',
          ...formatMcpDiagnostics(configured, statuses, mcpRef.current).split('\n'),
        ];
    setHelpPopupOpen(false);
    setContextPanel(null);
    setMcpPanel({
      title: mode === 'full' ? 'MCP Diagnostics' : 'MCP Summary',
      subtitle: configured.length === 0 ? 'No configured servers' : `${readyCount}/${totalCount} ready`,
      lines,
    });
  }, []);

  // Permission approval bridge — when PermissionManager blocks a tool, show UI and wait
  type PermissionRequestState = {
    toolName: string;
    description: string;
    details?: string;
    patternLabel?: string;
    onDecision: (action: 'allow' | 'always_allow' | 'deny') => void;
  };
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequestState | undefined>();
  const permissionResolveRef = useRef<((approved: boolean) => void) | null>(null);

  const handleApprovalNeeded = useCallback(async (request: import('@jarvis/tools').ApprovalRequest): Promise<boolean> => {
    return new Promise<boolean>((resolve) => {
      permissionResolveRef.current = resolve;
      const toolName = request.toolName;
      const description = request.reason;
      const details = request.risk === 'command' ? String(request.args?.command ?? '') : undefined;
      const patternLabel = request.argsKey || undefined;
      setPermissionRequest({
        toolName,
        description,
        details,
        patternLabel,
        onDecision: (action) => {
          setPermissionRequest(undefined);
          permissionResolveRef.current = null;
          if (action === 'always_allow') {
            // Approve this specific tool+args pattern for this session
            const pm = permManagerRef.current;
            if (pm) pm.approveToolPattern(toolName, request.argsKey);
            resolve(true);
          } else {
            resolve(action === 'allow');
          }
        },
      });
    });
  }, []);

  // Permission mode cycling (Shift+Tab) — suggest → auto-edit → full-auto → suggest
  const PERMISSION_CYCLE = ['workspace_write', 'accept_edits', 'bypass', 'plan'] as const;
  const PERMISSION_LABELS: Record<string, string> = {
    'workspace_write': 'suggest',
    'accept_edits': 'auto-edit',
    'bypass': 'full-auto',
    'plan': 'plan',
  };
  const handlePermissionModeCycle = useCallback(() => {
    const current = permissionModeRef.current;
    const idx = PERMISSION_CYCLE.indexOf(current as typeof PERMISSION_CYCLE[number]);
    const nextIdx = (idx + 1) % PERMISSION_CYCLE.length;
    const next = PERMISSION_CYCLE[nextIdx];
    permissionModeRef.current = next;
    saveSettings({ permission_mode: next as UserSettings['permission_mode'] });
    setModeVersion((v) => v + 1);
    // Update the state machine's base mode (it will sync to PermissionManager)
    stateMachineRef.current?.setBaseMode(next);
    // Also directly update PermissionManager in case state machine is not active
    permManagerRef.current?.setMode(next);
  }, []);

  const pushSpinnerDetail = useCallback((line: string | null) => {
    if (!line) return;
    setSpinnerDetails((prev) => {
      if (prev[prev.length - 1] === line) return prev;
      const next = [...prev, line];
      return next.length > 6 ? next.slice(-6) : next;
    });
  }, []);

  const startStreamingRun = useCallback((prompt: string) => {
    const runId = createUiMessageId('streamrun');
    streamingRunIdRef.current = runId;
    streamingSourceTextRef.current = '';
    streamingContentRef.current = null;
    setStreamingContent(null);
    emitDebugEvent({
      type: 'stream_run_started',
      runId,
      prompt,
      timestamp: Date.now(),
    });
    return runId;
  }, [emitDebugEvent]);

  const flushStreamingChunk = useCallback(() => {
    const runId = streamingRunIdRef.current;
    if (!runId) return null;
    if (!streamFlushRef.current && !streamAccumRef.current) {
      return streamingContentRef.current;
    }
    if (streamFlushRef.current) {
      clearTimeout(streamFlushRef.current);
      streamFlushRef.current = null;
    }
    const chunk = streamAccumRef.current;
    streamAccumRef.current = '';
    if (!chunk) return streamingContentRef.current;

    const decoded = decodeHtmlEntities(chunk);
    streamingSourceTextRef.current += decoded;
    const display = streamAssemblerRef.current.ingestDelta(
      runId,
      { content: [{ type: 'text', text: streamingSourceTextRef.current }] },
      false,
    );
    if (display !== null) {
      streamingContentRef.current = display;
      setStreamingContent(display);
      emitDebugEvent({
        type: 'stream_chunk_flushed',
        runId,
        chunkLength: decoded.length,
        displayLength: display.length,
        sourceLength: streamingSourceTextRef.current.length,
        timestamp: Date.now(),
      });
      return display;
    }
    return streamingContentRef.current;
  }, [emitDebugEvent]);

  const clearStreamingRun = useCallback((
    reason: 'tool_boundary' | 'turn_complete' | 'error' | 'abort' | 'cleanup',
  ) => {
    const runId = streamingRunIdRef.current;
    if (runId) {
      streamAssemblerRef.current.drop(runId);
      emitDebugEvent({
        type: 'stream_cleared',
        runId,
        reason,
        timestamp: Date.now(),
      });
    }
    streamingRunIdRef.current = null;
    pendingAssistantResumeRef.current = null;
    streamingSourceTextRef.current = '';
    streamingContentRef.current = null;
    streamAccumRef.current = '';
    if (streamFlushRef.current) {
      clearTimeout(streamFlushRef.current);
      streamFlushRef.current = null;
    }
    setStreamingContent(null);
  }, [emitDebugEvent]);

  const finalizeStreamingRun = useCallback((
    reason: 'tool_boundary' | 'turn_complete' | 'error' | 'abort' | 'cleanup',
    finalAnswer?: string | null,
  ): string | null => {
    const runId = streamingRunIdRef.current;
    const finalText = decodeHtmlEntities((finalAnswer ?? '').trim());
    flushStreamingChunk();

    if (!runId) {
      if (!finalText) return null;
      const messageId = createUiMessageId('msg');
      const msg: Message = {
        id: messageId,
        role: 'assistant',
        content: [{ type: 'text' as const, text: finalText }],
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, msg]);
      emitDebugEvent({ type: 'message_id_emitted', messageId, kind: 'assistant', timestamp: Date.now() });
      return finalText;
    }

    const streamedBeforeFinalize = streamingContentRef.current ?? '';
    const finalized = streamAssemblerRef.current.finalize(
      runId,
      finalText
        ? { content: [{ type: 'text', text: finalText }] }
        : { content: [{ type: 'text', text: streamingSourceTextRef.current }] },
      false,
    );
    const committedText = finalized.trim();
    emitDebugEvent({
      type: 'stream_finalized',
      runId,
      reason,
      finalAnswerLength: finalText.length,
      committedTextLength: committedText.length,
      replacedStreamed: Boolean(finalText) && finalText.trim() !== streamedBeforeFinalize.trim(),
      timestamp: Date.now(),
    });
    if (!committedText) {
      clearStreamingRun(reason);
      return null;
    }

    const messageId = createUiMessageId('msg');
    const msg: Message = {
      id: messageId,
      role: 'assistant',
      content: [{ type: 'text' as const, text: committedText }],
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, msg]);
    emitDebugEvent({ type: 'message_id_emitted', messageId, kind: 'assistant', timestamp: Date.now() });
    emitDebugEvent({
      type: 'stream_committed',
      runId,
      messageId,
      textLength: committedText.length,
      timestamp: Date.now(),
    });
    clearStreamingRun(reason);
    return committedText;
  }, [clearStreamingRun, emitDebugEvent, flushStreamingChunk]);

  // Set up the AskUserQuestion bridge for the tool
  useEffect(() => {
    setAskUserQuestionBridge((questions) => {
      return new Promise<Record<string, string>>((resolve, reject) => {
        askResolveRef.current = resolve;
        askRejectRef.current = reject;
        setAskQuestions(questions);
      });
    });
    return () => setAskUserQuestionBridge(null);
  }, []);

  // Set up the PlanReview bridge for exit_plan_mode (CC-style)
  useEffect(() => {
    setPlanReviewBridge((plan) => {
      return new Promise<PlanReviewDecision>((resolve) => {
        planReviewResolveRef.current = resolve;
        setMessages((prev) => [...prev, makeSysMsg(buildInlinePlanReviewText(plan))]);
        setPlanReview(plan);
        setPlanReviewIndex(0);
      });
    });
    return () => setPlanReviewBridge(null);
  }, []);

  // Initialize session store and restore previous session for this directory
  useEffect(() => {
    const store = new SessionStore();
    sessionStoreRef.current = store;

    const cwd = process.cwd();
    store.listSessions().then(async (sessionIds) => {
      let best: { id: string; updatedAt: string } | null = null;

      for (const sid of sessionIds) {
        try {
          const sidecar = await store.getSidecar(sid);
          if (sidecar.cwd === cwd) {
            if (!best || sidecar.updated_at > best.updatedAt) {
              best = { id: sid, updatedAt: sidecar.updated_at };
            }
          }
        } catch {
          // Skip sessions with missing sidecar
        }
      }

      if (best) {
        sessionIdRef.current = best.id;
        const rawMessages = await store.loadMessages(best.id);
        const chatMessages: ChatMessage[] = rawMessages.map((m) => {
          const meta = (m.metadata ?? {}) as Record<string, unknown>;
          return {
            role: m.role as ChatMessage['role'],
            content: m.content as string,
            messageId: m.message_id as string,
            toolCallId: m.tool_call_id as string | undefined,
            name: meta['_name'] as string | undefined,
            metadata: meta,
          };
        });
        historyRef.current = chatMessages;
      } else {
        const sid = `session_${crypto.randomUUID().slice(0, 12)}`;
        await store.createSession(sid, { cwd });
        sessionIdRef.current = sid;
      }

      sessionReadyRef.current = true;
    });
  }, []);

  // ── Config hot-reload watcher ──
  useEffect(() => {
    const watcher = new ConfigWatcher(process.cwd());
    watcher.onChange((event) => {
      if (event.type === 'user') {
        // Reload user config — resolve credentials per the new active model
        try {
          const config = JSON.parse(event.content) as Record<string, unknown>;
          const activeModel = (config['active_model'] as string) ?? (config['model'] as string);
          if (activeModel && typeof activeModel === 'string' && activeModel !== modelRef.current) {
            modelRef.current = activeModel;
            // Resolve provider credentials for the new model instead of
            // blindly applying top-level base_url/api_key overrides
            const creds = resolveModelCredentials(activeModel);
            if (creds.apiKey) apiKeyRef.current = creds.apiKey;
            if (creds.baseURL) baseURLRef.current = creds.baseURL;
          }
        } catch { /* ignore parse errors */ }
      }
      if (event.type === 'mcp') {
        // MCP config changed — disconnect and invalidate agent for reconnect
        if (mcpRef.current) {
          mcpRef.current.disconnectAll();
        }
        invalidateAgent();
      }
    });
    watcher.start();
    return () => watcher.stop();
  }, []);

  const getAgent = useCallback((): AgentLoop => {
    if (!agentRef.current) {
      if (!eventBusRef.current) {
        eventBusRef.current = new AgentEventBus();
      }
      const eventBus = eventBusRef.current;
      const bindProgressEvent = (eventName: string) => {
        eventBus.on(eventName, (payload) => {
          if (eventName === 'turn:phase') {
            emitDebugEvent({
              type: 'turn_phase',
              phase: payload.phase === 'finalize' ? 'finalize' : payload.phase === 'analyze' ? 'analyze' : 'discover',
              detail: typeof payload.detail === 'string' ? payload.detail : 'phase_update',
              step: typeof payload.step === 'number' ? payload.step : undefined,
              finalizeReason: payload.finalizeReason === 'stagnation' || payload.finalizeReason === 'rejections'
                ? payload.finalizeReason
                : payload.finalizeReason === null
                  ? null
                  : undefined,
              finalizeAttempts: typeof payload.finalizeAttempts === 'number' ? payload.finalizeAttempts : undefined,
              toolCallsSoFar: typeof payload.toolCallsSoFar === 'number' ? payload.toolCallsSoFar : undefined,
              toolCallCount: typeof payload.toolCallCount === 'number' ? payload.toolCallCount : undefined,
              retryWithToolInstructionCount: typeof payload.retryWithToolInstructionCount === 'number'
                ? payload.retryWithToolInstructionCount
                : undefined,
              noProgressCount: typeof payload.noProgressCount === 'number' ? payload.noProgressCount : undefined,
              timestamp: Date.now(),
            });
          }
          pushSpinnerDetail(summarizeAgentEventProgress(eventName, payload));
          if (eventName === 'llm:request') {
            setSpinnerStatus('preparing the next step');
          }
          if (eventName === 'tool:executing') {
            setSpinnerStatus(`using ${humanizeToolName(payload.toolName)}`);
          }
          if (eventName === 'turn:warning' && typeof payload.warning === 'string') {
            setSpinnerStatus(payload.warning);
          }
          if (eventName === 'turn:phase') {
            const detail = typeof payload.detail === 'string' ? payload.detail : '';
            if (detail === 'enter_finalize') {
              setSpinnerStatus('finalizing from collected results');
            } else if (detail.includes('forced_synthesis') || detail.includes('forcing_')) {
              setSpinnerStatus('synthesizing the final answer');
            }
          }
          if (eventName === 'turn:complete' && typeof payload.stopReason === 'string') {
            setSpinnerStatus('finalizing the response');
          }
        });
      };
      eventBus.on('context:compressing', () => {
        compactedCountRef.current++;
        peakContextRef.current = 0; // reset peak — compaction freed space
        setCompactedVersion((v) => v + 1);
      });
      for (const eventName of ['turn:start', 'skills:matched', 'llm:request', 'llm:response', 'tool:executing', 'tool:result', 'turn:warning', 'turn:phase', 'turn:complete']) {
        bindProgressEvent(eventName);
      }
      eventBus.on('context_window_usage', (payload) => {
        const used = Number(payload.used_tokens ?? 0);
        const window = Number(payload.context_window ?? tokenTrackerRef.current?.contextWindow ?? 200_000);
        const pct = Number(payload.usage_pct ?? (window > 0 ? used / window : 0));
        const messageCount = Number(payload.message_count ?? 0);
        // Track peak usage so the bar doesn't oscillate between turns
        // (a new turn starts with smaller context before tool results accumulate)
        const peakUsed = Math.max(used, peakContextRef.current);
        const peakPct = window > 0 ? peakUsed / window : 0;
        peakContextRef.current = peakUsed;
        const prev = liveContextUsageRef.current;
        liveContextUsageRef.current = {
          ...(prev ?? {
            contextWindow: window,
            usedTokens: peakUsed,
            usagePct: peakPct,
            messageCount,
          }),
          contextWindow: window,
          usedTokens: peakUsed,
          usagePct: peakPct,
          messageCount,
        };
        setContextUsageVersion((v) => v + 1);
      });
      eventBus.on('context_usage_breakdown', (payload) => {
        const prev = liveContextUsageRef.current;
        const contextWindow = Number(payload.context_window ?? prev?.contextWindow ?? tokenTrackerRef.current?.contextWindow ?? 200_000);
        const estimatedTotal = Number(payload.estimated_total_tokens ?? 0);
        const estimatedUsagePct = contextWindow > 0 ? (estimatedTotal / contextWindow) : 0;
        liveContextUsageRef.current = {
          ...(prev ?? {
            contextWindow,
            usedTokens: Number(payload.estimated_total_tokens ?? payload.used_tokens ?? 0),
            usagePct: estimatedUsagePct,
            messageCount: Number(payload.message_count ?? 0),
          }),
          contextWindow,
          usedTokens: estimatedTotal > 0 ? estimatedTotal : (prev?.usedTokens ?? 0),
          usagePct: estimatedUsagePct,
          systemPromptTokens: Number(payload.system_prompt_tokens ?? 0),
          projectContextTokens: Number(payload.project_context_tokens ?? 0),
          skillsTokens: Number(payload.skills_tokens ?? 0),
          memoryTokens: Number(payload.memory_tokens ?? 0),
          conversationTokens: Number(payload.conversation_tokens ?? 0),
          toolSchemasTokens: Number(payload.tool_schemas_tokens ?? 0),
          mcpToolsTokens: Number(payload.mcp_tools_tokens ?? 0),
          estimatedTotalTokens: estimatedTotal,
        };
        setContextUsageVersion((v) => v + 1);
      });

      const tools = new ToolRegistry();
      for (const tool of allBuiltinTools) {
        tools.register(tool);
      }
      // Register web tools (mirrors CLI main.ts registerWebTools)
      {
        tools.register(webSearchTool);
        tools.register(webFetchTool);
        const tavilySearch = tryCreateTavilySearch();
        const tavilyFetch = tryCreateTavilyFetch();
        if (tavilySearch) { tools.register(createTavilySearchTool(tavilySearch)); }
        if (tavilyFetch) { tools.register(createTavilyFetchTool(tavilyFetch)); }
      }
      // Memory search/get tools (mirrors CLI main.ts bootstrap)
      {
        const memoryStore = new MarkdownMemoryStore();
        tools.register({
          name: 'memory_search',
          toolset: 'memory',
          description: 'Search persistent memory entries by keyword',
          isAsync: true,
          schema: {
            type: 'function',
            function: {
              name: 'memory_search',
              description: 'Search persistent memory entries by keyword',
              parameters: {
                type: 'object',
                properties: {
                  query: { type: 'string', description: 'Search query' },
                  maxResults: { type: 'number', description: 'Max results (default 5)' },
                  memoryType: { type: 'string', description: 'Filter by type: user, project, feedback, reference' },
                },
                required: ['query'],
              },
            },
          },
          handler: (args: Record<string, unknown>) => createMemorySearchHandler(memoryStore)(args),
        });
        tools.register({
          name: 'memory_get',
          toolset: 'memory',
          description: 'Read a specific memory entry by name',
          isAsync: true,
          schema: {
            type: 'function',
            function: {
              name: 'memory_get',
              description: 'Read a specific memory entry by name',
              parameters: {
                type: 'object',
                properties: {
                  name: { type: 'string', description: 'Memory entry name' },
                },
                required: ['name'],
              },
            },
          },
          handler: (args: Record<string, unknown>) => createMemoryGetHandler(memoryStore)(args),
        });
        tools.register({
          name: 'memory_write',
          toolset: 'memory',
          description: 'Save important information to persistent memory (user preferences, project facts, decisions, schedules)',
          isAsync: true,
          schema: {
            type: 'function',
            function: {
              name: 'memory_write',
              description: 'Save important information to persistent memory. Use this proactively when the user mentions preferences, schedules, ideas, corrections, or important facts.',
              parameters: {
                type: 'object',
                properties: {
                  name: { type: 'string', description: 'Short kebab-case name for this memory (e.g., prefers-vim, deploy-friday, identity-timezone)' },
                  description: { type: 'string', description: 'One-line summary of what this memory contains' },
                  content: { type: 'string', description: 'The full memory content in markdown' },
                  memoryType: { type: 'string', description: 'Category: user (identity, preferences, habits, schedule, ideas), project (facts, architecture, conventions), feedback (corrections), reference (external info)' },
                  tags: { type: 'array', items: { type: 'string' }, description: 'Fine-grained tags: identity, preferences, habits, schedule, ideas, code-style, architecture, conventions, research' },
                },
                required: ['name', 'content'],
              },
            },
          },
          handler: (args: Record<string, unknown>) => createMemoryWriteHandler(memoryStore)(args),
        });
        tools.register({
          name: 'memory_delete',
          toolset: 'memory',
          description: 'Delete an outdated or conflicting memory entry',
          isAsync: true,
          schema: {
            type: 'function',
            function: {
              name: 'memory_delete',
              description: 'Delete a memory entry by name. Use when you find conflicting memories or when the user corrects outdated information.',
              parameters: {
                type: 'object',
                properties: {
                  name: { type: 'string', description: 'Name of the memory entry to delete' },
                  reason: { type: 'string', description: 'Why this memory is being deleted (for audit)' },
                },
                required: ['name'],
              },
            },
          },
          handler: (args: Record<string, unknown>) => createMemoryDeleteHandler(memoryStore)(args),
        });
      }
      toolsRef.current = tools;

      if (!skillsRef.current) {
        const pluginSkillDirs = discoverPluginSkillDirs(process.cwd());
        skillsRef.current = new SkillRegistry();
        skillsRef.current.discover({
          builtinDir: 'skills',
          projectDir: '.jarvis/skills',
          extraDirs: pluginSkillDirs.map((p) => ({ path: p, source: 'plugin' as const })),
        });
      }
      if (!executorRef.current) {
        executorRef.current = new SkillExecutor(skillsRef.current);
      }
      tools.register(createSkillLoadTool(skillsRef.current));
      tools.register(createSkillTool(skillsRef.current));

      // MCP client — wire resource listing/reading tools + dynamic tool exposure
      if (!mcpRef.current) {
        mcpRef.current = new MCPClient();
      }
      tools.register(createListMcpResourcesTool(mcpRef.current));
      tools.register(createReadMcpResourceTool(mcpRef.current));
      tools.register(createMcpStatusTool(mcpRef.current));
      tools.register(createMcpHealthcheckTool(mcpRef.current));
      // User-level + project-level (project overrides same-id) + plugin
      const userServers = discoverUserMcpServers(process.cwd());
      const projectServers = discoverProjectMcpServers(process.cwd());
      const pluginServers = discoverPluginMcpServers(process.cwd());
      // Merge: project overrides user (same id), then add plugins
      const mergedIds = new Set<string>();
      const mcpServers: Array<{ id: string; plugin?: string; config: McpServerConfig }> = [];
      for (const s of projectServers) { mergedIds.add(s.id); mcpServers.push(s); }
      for (const s of userServers) { if (!mergedIds.has(s.id)) { mergedIds.add(s.id); mcpServers.push(s); } }
      for (const s of pluginServers) { if (!mergedIds.has(s.id)) { mcpServers.push(s); } }
      mcpConfiguredRef.current = mcpServers;
      if (mcpServers.length > 0) {
        // Build tool filter map from config
        const toolFilters = new Map<string, { include?: string[]; exclude?: string[] }>();
        for (const s of mcpServers) {
          if (s.config.tools_include || s.config.tools_exclude) {
            toolFilters.set(s.id, {
              include: s.config.tools_include,
              exclude: s.config.tools_exclude,
            });
          }
        }
        void connectMcpServers(mcpRef.current, mcpServers).then((statuses) => {
          mcpStatusesRef.current = statuses;
          setMcpStatusVersion((v) => v + 1);
          for (const mcpTool of createMcpToolEntries(mcpRef.current!, toolFilters)) {
            try {
              tools.register(mcpTool);
            } catch {
              // ignore duplicate dynamic tool registration
            }
          }
        });
      }
      for (const mcpTool of createMcpToolEntries(mcpRef.current)) {
        tools.register(mcpTool);
      }

      // Subagent pool — wire Agent tool with agent store updates
      if (!poolRef.current) {
        poolRef.current = new SubagentPool();
        poolRef.current.setParentMailbox(mailboxRef.current);

        // Wire pool status updates to agent store for TUI panel
        poolRef.current.onStatusUpdate = (entry) => {
          import('./agent-store.js').then(({ agentStore }) => {
            const existing = agentStore.getSnapshot().find((a) => a.agentId === entry.agentId);
            agentStore.upsert({
              agentId: entry.agentId,
              status: entry.status,
              role: entry.role ?? existing?.role ?? 'unknown',
              depth: entry.depth ?? existing?.depth ?? 0,
              parentId: entry.parentId ?? existing?.parentId ?? null,
              task: entry.task ?? existing?.task,
              startedAt: existing?.startedAt ?? Date.now(),
              reviewStatus: entry.reviewStatus ?? existing?.reviewStatus,
              confidence: entry.confidence ?? existing?.confidence,
              findingsCount: entry.findingsCount ?? existing?.findingsCount,
            });
          });
        };
        const subagentRunner = new SubagentRunner({
          createAgentLoop: ({
            agentId,
            allowedTools,
            maxSteps,
            depth,
            mailbox,
            systemPrompt,
          }) => {
            const subTools = new ToolRegistry();
            for (const tool of allBuiltinTools) {
              if (!allowedTools || allowedTools.includes(tool.name)) {
                subTools.register(tool);
              }
            }
            subTools.register(createSkillLoadTool(skillsRef.current!));
            subTools.register(createSkillTool(skillsRef.current!));

            const subRuntime = createToolRuntime(subTools, {
              permissionMode: permissionModeRef.current,
              sandbox: loadJarvisConfig().sandbox,
              projectRoot: process.cwd(),
              onLifecycleEvent: handleToolRuntimeLifecycle,
            });

            return new AgentLoop({
              model: {
                model: modelRef.current,
                apiKey: apiKeyRef.current,
                baseURL: baseURLRef.current,
                reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
              },
              maxTurns: maxSteps,
              maxSteps,
              systemPrompt,
              tools: subTools,
              toolRuntime: subRuntime,
              provider: new LLMProvider({
                model: modelRef.current,
                apiKey: apiKeyRef.current,
                baseURL: baseURLRef.current,
                reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
              }),
              skillRegistry: skillsRef.current!,
              skillExecutor: executorRef.current!,
              hooks: new HookRegistry(),
              mailbox,
              permissionMode: permissionModeRef.current,
              projectRoot: process.cwd(),
              eventBus: new AgentEventBus(),
            });
          },
        });
        poolRef.current.setRunner((config, mailbox) => subagentRunner.run(config, mailbox));
      }
      tools.register(createAgentTool(poolRef.current));

      if (!tokenTrackerRef.current) {
        const mainProvider = new LLMProvider({
          model: modelRef.current,
          apiKey: apiKeyRef.current,
          baseURL: baseURLRef.current,
          reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
        });
        tokenTrackerRef.current = new TokenTracker(mainProvider.contextWindow);
      }
      agentRef.current = new AgentLoop({
        model: {
          model: modelRef.current,
          apiKey: apiKeyRef.current,
          baseURL: baseURLRef.current,
          reasoningEffort: reasoningEffortRef.current as ModelReasoningEffort,
        },
        maxTurns: options.maxTurns,
        maxSteps: options.maxSteps,
        timeoutS: options.timeoutS,
        toolTimeoutS: options.toolTimeoutS,
        systemPrompt: options.systemPrompt,
        eventBus,
        onThreadEvent: (event) => {
          threadEventsRef.current.push(event);
          setThreadEvents((prev) => [...prev, event]);
        },
        tools,
        skillRegistry: skillsRef.current,
        skillExecutor: executorRef.current,
        tokenTracker: tokenTrackerRef.current,
        onToken: (token: string) => {
          if (runStatsRef.current) {
            runStatsRef.current.tokenEvents += 1;
            runStatsRef.current.tokenChars += token.length;
            runStatsRef.current.hadStreamingContent = true;
          }
          const streamRunStart = resolveContentTokenStreamStart({
            hasActiveRun: Boolean(streamingRunIdRef.current),
            pendingResumeReason: pendingAssistantResumeRef.current,
          });
          if (streamRunStart.shouldStartRun && streamRunStart.label) {
            startStreamingRun(streamRunStart.label);
          }
          pendingAssistantResumeRef.current = streamRunStart.pendingResumeReason;
          // First content token: flush live reasoning as thinking block
          if (!reasoningFlushedRef.current && reasoningBufferRef.current) {
            const thinkingText = reasoningBufferRef.current;
            reasoningFlushedRef.current = true;
            setStreamingThinking(null);
            if (thinkingText.length > 20) {
              const messageId = createUiMessageId('thinking');
              setMessages((prev) => [...prev, {
                id: messageId,
                role: 'assistant',
                content: [{ type: 'thinking' as const, text: thinkingText.slice(0, 65536) }],
                timestamp: Date.now(),
              }]);
              emitDebugEvent({ type: 'message_id_emitted', messageId, kind: 'thinking', timestamp: Date.now() });
            }
            setSpinnerStatus('drafting the response');
          }
          // Skip DSML tool call tags leaked into visible text
          if (token.includes('｜')) return;
          // Buffer tokens and flush periodically (append mode)
          streamAccumRef.current += token;
          if (!streamFlushRef.current) {
            streamFlushRef.current = setTimeout(() => {
              flushStreamingChunk();
            }, 50);
          }
        },
        onReasoningDelta: (delta: string) => {
          const displayDelta = sanitizeReasoningForDisplay(delta);
          if (!displayDelta) {
            return;
          }
          if (runStatsRef.current) {
            runStatsRef.current.reasoningEvents += 1;
            runStatsRef.current.reasoningChars += displayDelta.length;
            runStatsRef.current.hadStreamingThinking = true;
          }
          const buf = reasoningBufferRef.current + displayDelta;
          const displayBuffer = sanitizeReasoningForDisplay(buf);
          if (!displayBuffer) {
            return;
          }
          reasoningBufferRef.current = displayBuffer.length > 262144 ? displayBuffer.slice(-262144) : displayBuffer;
          // Live thinking display: throttle React state updates (CC/OpenClaw pattern)
          const now = Date.now();
          if (now - reasoningDisplayThrottle.current > 200) {
            reasoningDisplayThrottle.current = now;
            setStreamingThinking(reasoningBufferRef.current);
          }
          const boldMatch = displayDelta.match(/\*\*([^*]+)\*\*/);
          if (boldMatch) {
            setSpinnerVerb(boldMatch[1]);
          } else if (!spinnerVerb) {
            const clean = displayDelta.replace(/[#*`\n]/g, ' ').replace(/\s+/g, ' ').trim();
            if (clean.length > 10) setSpinnerVerb(clean.slice(0, 60));
          }
        },
        onToolStart: (callId, toolName, args) => {
          if (runStatsRef.current) {
            runStatsRef.current.toolStarts += 1;
          }
          emitDebugEvent({
            type: 'tool_started',
            toolName,
            callId,
            timestamp: Date.now(),
          });
          const boundaryTransition = resolveToolBoundaryStreamTransition({
            hasActiveRun: Boolean(streamingRunIdRef.current),
          });
          if (boundaryTransition.shouldFinalizeCurrentRun) {
            finalizeStreamingRun('tool_boundary');
          }
          pendingAssistantResumeRef.current = boundaryTransition.pendingResumeReason;
          const argRecord = typeof args === 'object' && args !== null
            ? (args as Record<string, unknown>)
            : undefined;
          const input = formatToolLine(toolName, argRecord);
          setMessages((prev) => [...prev, {
            id: `tool_${callId}`,
            role: 'assistant',
            content: [{
              type: 'tool_use' as const,
              toolName,
              input,
              status: 'running' as const,
            }],
            timestamp: Date.now(),
          }]);
        },
        onToolEnd: (callId, toolName, result) => {
          if (runStatsRef.current) {
            runStatsRef.current.toolEnds += 1;
          }
          emitDebugEvent({
            type: 'tool_finished',
            toolName,
            callId,
            ok: result.ok,
            resultLength: result.content.length,
            timestamp: Date.now(),
          });
          updateToolMessageLifecycle(callId, {
            status: result.ok ? 'success' : 'error',
            result: result.content.slice(0, 2000),
            durationMs: result.durationMs,
          });
        },
        mailbox: mailboxRef.current,
        sessionStore: sessionStoreRef.current ?? undefined,
        toolRuntime: (() => {
          const runtime = createToolRuntime(tools, {
            permissionMode: permissionModeRef.current,
            sandbox: loadJarvisConfig().sandbox,
            projectRoot: process.cwd(),
            onApprovalNeeded: handleApprovalNeeded,
            onLifecycleEvent: handleToolRuntimeLifecycle,
          });
          permManagerRef.current = runtime.getPermissionManager() ?? null;
          stateMachineRef.current = runtime.getStateMachine() ?? null;
          // Subscribe to state changes for UI updates
          stateMachineRef.current?.onStateChange((newState) => {
            setPermissionState(newState);
            setModeVersion((v) => v + 1);
          });
          return runtime;
        })(),
      });
    }
    return agentRef.current;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [options]);

  const onSubmit = useCallback(async (prompt: string) => {
    // Interrupt any in-progress run (supports type-ahead)
    agentRef.current?.interrupt('superseded_by_new_prompt');
    if (abortRef.current) {
      abortRef.current.abort();
    }

    const turnStartedAt = Date.now();
    runStatsRef.current = {
      prompt,
      startedAt: turnStartedAt,
      trackerStartBlended: tokenTrackerRef.current?.totalBlended ?? 0,
      tokenEvents: 0,
      tokenChars: 0,
      reasoningEvents: 0,
      reasoningChars: 0,
      toolStarts: 0,
      toolEnds: 0,
      hadStreamingContent: false,
      hadStreamingThinking: false,
    };
    emitDebugEvent({
      type: 'run_started',
      prompt,
      timestamp: turnStartedAt,
    });

    const userMsg: Message = {
      id: createUiMessageId('msg'),
      role: 'user',
      content: prompt,
      timestamp: Date.now(),
    };
      setMessages((prev) => [...prev, userMsg]);
      emitDebugEvent({ type: 'message_id_emitted', messageId: userMsg.id, kind: 'user', timestamp: Date.now() });
      setIsLoading(true);
      // Fire state machine transition for user submit
      stateMachineRef.current?.transition({ type: 'user_submit' });
      clearStreamingRun('cleanup');
        setStreamingThinking(null);
        setSpinnerVerb('Concocting');
        setSpinnerStatus(undefined);
        setSpinnerDetails([]);
        setSpinnerCompleted([]);
        setSpinnerRunning(undefined);
        toolLifecycleStateRef.current = createToolLifecycleState();
        reasoningBufferRef.current = '';
      reasoningDisplayThrottle.current = 0;
      reasoningFlushedRef.current = false;
      startStreamingRun(prompt);

    // Create abort controller for this run
    const abort = new AbortController();
    abortRef.current = abort;

    // Start elapsed timer
    const startTime = Date.now();
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    elapsedRef.current = 0;
    setElapsedMs(0);
    elapsedTimerRef.current = setInterval(() => {
      elapsedRef.current = Date.now() - startTime;
      setElapsedMs(elapsedRef.current);
    }, 1000);

    try {
      if (abort.signal.aborted) throw new DOMException('Aborted', 'AbortError');

      const agent = getAgent();
      const store = sessionStoreRef.current;
      const sid = sessionIdRef.current!;

      // Persist user message to session store (truth source for runTurn context)
      if (store && sid) {
        await store.appendMessage(sid, 'user', prompt, { turnId: undefined });
      }
      // Keep historyRef for slash-command compat (display layer only)
      historyRef.current = [...historyRef.current, {
        role: 'user',
        content: prompt,
        messageId: `msg_${crypto.randomUUID()}`,
      }];

      const result = await agent.runTurn(prompt, {
        sessionId: sid ?? undefined,
        cwd: process.cwd(),
      });

      // Persist tool calls + results to session store (for accurate history token counting)
      if (store && sid) {
        // Save assistant message with tool_calls metadata
        if (result.toolCalls.length > 0) {
          const toolCallsMeta = result.toolCalls.map(tc => ({
            id: tc.callId,
            type: 'function' as const,
            function: { name: tc.name, arguments: JSON.stringify(tc.arguments) },
          }));
          await store.appendMessage(sid, 'assistant', '', {
            turnId: result.turnId,
            metadata: { tool_calls: toolCallsMeta },
          });
          // Save each tool result
          for (let i = 0; i < result.toolResults.length; i++) {
            const tr = result.toolResults[i];
            const callId = result.toolCalls[i]?.callId ?? `call_${i}`;
            const toolName = (tr['name'] as string) ?? result.toolCalls[i]?.name ?? 'unknown';
            await store.appendMessage(sid, 'tool', String(tr['content'] ?? ''), {
              turnId: result.turnId,
              toolCallId: callId,
              metadata: { tool_name: toolName },
            });
          }
        }
        // Persist final answer
        if (result.finalAnswer) {
          await store.saveFinalAnswer(sid, result.turnId, result.finalAnswer);
        }
      }

      // Track files modified by this turn
      for (const tr of result.toolResults) {
        const name = tr['name'] as string ?? '';
        if (FILE_MODIFYING_TOOLS.has(name)) {
          const files = extractModifiedFiles(name, tr['content'] as string ?? '');
          for (const f of files) {
            modifiedFilesRef.current.add(f);
          }
        }
      }

      const finalAnswer = typeof result.finalAnswer === 'string' ? result.finalAnswer.trim() : '';

      // Check if the result is a failure (e.g., model call failed)
        if (!result.ok || result.status === 'failed') {
          finalizeStreamingRun('error');
          const toolSummary = buildToolLifecycleSummary(toolLifecycleStateRef.current);
          setSpinnerRunning(toolSummary.runningLine);
          setSpinnerStatus(toolSummary.statusLine);
          const errorContent: MessageContent = {
          type: 'error',
          message: decodeHtmlEntities(finalAnswer) || 'Model call failed',
        };
        const errMsg: Message = {
          id: createUiMessageId('msg'),
          role: 'assistant',
          content: [errorContent],
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, errMsg]);
        emitDebugEvent({ type: 'message_id_emitted', messageId: errMsg.id, kind: 'error', timestamp: Date.now() });

        // Emit debug event for failure
        emitDebugEvent({
          type: 'run_failed',
          prompt,
          turnState: result.turnState,
          elapsedMs: Date.now() - turnStartedAt,
          error: finalAnswer,
          stopReason: result.stopReason,
          timestamp: Date.now(),
        });

        // Skip normal message processing
        return;
      }

      // Finalize the current streaming run before building any non-text blocks.
        const committedStreamingText = finalizeStreamingRun('turn_complete', result.finalAnswer);
        const toolSummary = buildToolLifecycleSummary(toolLifecycleStateRef.current);
        setSpinnerRunning(toolSummary.runningLine);
        setSpinnerStatus(toolSummary.statusLine);

      const content: MessageContent[] = [];
      let taskSnapshot: CodexTaskSnapshot | null = null;

      // Show reasoning as a collapsible thinking block
      const displayReasoning = result.reasoning ? sanitizeReasoningForDisplay(result.reasoning) : '';
      if (displayReasoning) {
        content.push({
          type: 'thinking',
          text: displayReasoning,
        });
      }

      // Collect file changes for summary display
      const fileChanges: FileChange[] = [];
      for (const tr of result.toolResults) {
        const name = tr['name'] as string ?? '';
        const trContent = tr['content'] as string ?? '';
        const change = computeFileChange(name, trContent);
        if (change) fileChanges.push(change);

        const parsed = parseToolContent(name, trContent);
        if (parsed) {
          if (parsed.type === 'task_result' && parsed.counts) {
            taskCountRef.current = parsed.counts;
            taskSnapshot = {
              turnId: result.turnId,
              sourceId: `task_snapshot_${result.turnId}`,
              counts: parsed.counts,
              tasks: parsed.tasks,
            };
          } else {
            content.push(parsed);
          }
        }
        // Note: tool_use blocks already pushed via onToolStart/onToolEnd
        // during agent execution — skip here to avoid duplicates.
      }

      // Preserve the final answer unless the trailing streamed text already
      // rendered the same content. Decode HTML entities that models
      // (especially DeepSeek) emit in text — &quot; &amp; &lt; etc.

      // Append file change summary if any files were modified
      if (fileChanges.length > 0) {
        content.push({
          type: 'diff',
          filename: `Changes (${fileChanges.length} file${fileChanges.length > 1 ? 's' : ''})`,
          diff: formatFileChangeSummary(fileChanges),
        });
      }

      if (content.length > 0) {
        const assistantMsg: Message = {
          id: createUiMessageId('msg'),
          role: 'assistant',
          content,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, assistantMsg]);
        emitDebugEvent({ type: 'message_id_emitted', messageId: assistantMsg.id, kind: 'assistant', timestamp: Date.now() });
      }

      if (taskSnapshot) {
        setCodexTaskSnapshots((prev) => [
          ...prev.filter((snapshot) => snapshot.turnId !== taskSnapshot!.turnId),
          taskSnapshot!,
        ]);
      }

      const turnTokenCount = estimateTurnTokenCount(runStatsRef.current, tokenTrackerRef.current);
      setCodexTurnSnapshots((prev) => [
        ...prev.filter((snapshot) => snapshot.turnId !== result.turnId),
        {
          turnId: result.turnId,
          elapsedMs: Date.now() - turnStartedAt,
          tokenCount: turnTokenCount,
        },
      ]);

      const stats = runStatsRef.current;
      const reasoningText = result.reasoning ?? '';
      const liveStreamingText = streamingContentRef.current ?? '';
      const committedText = committedStreamingText ?? '';
      const resultAnswer = result.finalAnswer ?? '';
      emitDebugEvent({
        type: 'run_completed',
        prompt,
        turnState: result.turnState,
        elapsedMs: Date.now() - turnStartedAt,
        finalAnswerLength: resultAnswer.length,
        finalAnswerPreview: resultAnswer.slice(0, 200),
        finalAnswerTail: resultAnswer.slice(-200),
        reasoningLength: reasoningText.length,
        streamedContentLength: liveStreamingText.length,
        committedStreamingLength: committedText.length,
        tokenEvents: stats?.tokenEvents ?? 0,
        tokenChars: stats?.tokenChars ?? 0,
        reasoningEvents: stats?.reasoningEvents ?? 0,
        reasoningChars: stats?.reasoningChars ?? 0,
        toolStarts: stats?.toolStarts ?? 0,
        toolEnds: stats?.toolEnds ?? 0,
        hadStreamingContent: stats?.hadStreamingContent ?? false,
        hadStreamingThinking: stats?.hadStreamingThinking ?? false,
        toolResultCount: result.toolResults.length,
        stopReason: result.stopReason,
        turnsUsed: result.toolCalls.length,
        toolResults: result.toolResults.map((tr: Record<string, unknown>) => ({
          name: tr['name'] as string ?? '',
          ok: tr['ok'] as boolean ?? false,
          contentLength: typeof tr['content'] === 'string' ? (tr['content'] as string).length : 0,
          error: tr['error'] as string | undefined,
        })),
        newMessageCount: 1,
        timestamp: Date.now(),
      });

      // Append assistant message to historyRef for display/slash-command compat
      if (result.finalAnswer) {
        historyRef.current = [...historyRef.current, {
          role: 'assistant' as const,
          content: result.finalAnswer,
          messageId: `msg_${crypto.randomUUID()}`,
        }];
      }
      } catch (err) {
      const toolSummary = buildToolLifecycleSummary(toolLifecycleStateRef.current);
      setSpinnerRunning(toolSummary.runningLine);
      setSpinnerStatus(toolSummary.statusLine);
        const isAbort = err instanceof DOMException && err.name === 'AbortError';
      const stats = runStatsRef.current;
      emitDebugEvent({
        type: 'run_failed',
        prompt,
        turnState: isAbort ? 'interrupted' : 'failed',
        elapsedMs: Date.now() - turnStartedAt,
        tokenEvents: stats?.tokenEvents ?? 0,
        tokenChars: stats?.tokenChars ?? 0,
        reasoningEvents: stats?.reasoningEvents ?? 0,
        reasoningChars: stats?.reasoningChars ?? 0,
        toolStarts: stats?.toolStarts ?? 0,
        toolEnds: stats?.toolEnds ?? 0,
        hadStreamingContent: stats?.hadStreamingContent ?? false,
        hadStreamingThinking: stats?.hadStreamingThinking ?? false,
        error: err instanceof Error ? err.message : String(err),
        isAbort,
        timestamp: Date.now(),
      });
      const errorContent: MessageContent = isAbort
        ? { type: 'text', text: 'Conversation interrupted.' }
        : { type: 'error', message: err instanceof Error ? err.message : String(err) };
      const errMsg: Message = {
        id: createUiMessageId('msg'),
        role: 'assistant',
        content: [errorContent],
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errMsg]);
      emitDebugEvent({ type: 'message_id_emitted', messageId: errMsg.id, kind: 'error', timestamp: Date.now() });
    } finally {
      // Cleanup: commit any remaining text (handles error/abort path —
      finalizeStreamingRun(abortRef.current ? 'abort' : 'cleanup');
      abortRef.current = null;
      setIsLoading(false);
      // Fire state machine transition for turn completion
      stateMachineRef.current?.transition({ type: 'turn_complete' });
      clearStreamingRun('cleanup');
      // Stop elapsed timer
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
      setElapsedMs(elapsedRef.current);
      runStatsRef.current = null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [getAgent, options.model]);

  const replCommands: REPLCommandDef[] = useMemo(
    () =>
      buildReplCommands(
        {
          store: sessionStoreRef.current,
          sid: sessionIdRef.current,
          skills: skillsRef.current,
          historyRef,
          messages,
          setMessages,
          setIsLoading,
          cwd: process.cwd(),
          modelRef,
          apiKeyRef,
          baseURLRef,
          reasoningEffortRef,
          systemPromptRef,
          modifiedFilesRef,
          getAgent,
          invalidateAgent,
          onModelChange: () => setModelVersion((v) => v + 1),
          maxTurns: options.maxTurns,
          outputStyleRef,
          permissionModeRef,
          permManagerRef,
          mcpClientRef: mcpRef,
          mcpStatusesRef,
          mcpConfiguredRef,
          tokenTrackerRef,
          toolsRef,
          liveContextUsageRef,
        },
        setMessages,
        skillsRef.current,
        setModelSelectorOpen,
        setEffortSelectorOpen,
        setHelpPopupOpen,
      ),
    // Rebuild only when getAgent changes (lazy init via useCallback)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [getAgent, invalidateAgent, options.maxTurns, messages],
  );

  useEffect(() => {
    try {
      getAgent();
    } catch {
      // Best-effort prewarm only.
    }
  }, [getAgent]);

  // Wire cron scheduler to auto-submit prompts when schedule_wakeup fires.
  // This enables the CC-style "wake up and continue working" pattern.
  const onSubmitRef = useRef(onSubmit);
  onSubmitRef.current = onSubmit;
  useEffect(() => {
    const scheduler = getCronScheduler();
    scheduler.onFireCallback((job) => {
      // Automatically submit the wakeup prompt as a new user message
      onSubmitRef.current?.(job.prompt);
    });
  }, []);

  const statusSegments: StatusLineSegment[] = useMemo(() => {
    const tracker = tokenTrackerRef.current;
    const liveUsage = liveContextUsageRef.current;
    const liveUsedPct = liveUsage
      ? Math.max(0, Math.min(100, liveUsage.usagePct * 100))
      : undefined;
    const liveContextRemaining = liveUsedPct !== undefined
      ? Math.max(0, Math.min(100, 100 - liveUsedPct))
      : undefined;
    return buildStatusSegments({
      cwd,
      model: parseModelName(modelRef.current).cleanName,
      gitBranch,
      effort: reasoningEffortRef.current,
      permissionMode: permissionModeRef.current,
      permissionState: permissionState !== 'idle' ? permissionState : undefined,
      isLoading,
      hasQuestion: askQuestions !== null,
      totalTokens: liveUsage?.usedTokens ?? (tracker?.turnCount ? tracker.currentContextTokens : undefined),
      contextPercentRemaining: liveContextRemaining ?? tracker?.contextPercentRemaining,
      contextWindow: tracker?.contextWindow ?? resolveContextWindow(modelRef.current),
      taskCounts: taskCountRef.current,
      elapsedMs,
      agentCounts: {
        total: agentEntries.length,
        running: agentEntries.filter((a) => a.status === 'running').length,
        completed: agentEntries.filter((a) => a.status === 'completed').length,
      },
      sessionId: sessionIdRef.current,
    });
  }, [agentEntries, askQuestions, contextUsageVersion, cwd, elapsedMs, gitBranch, isLoading, messages.length, modeVersion, modelVersion]);

  const statusDetailLines = useMemo(() => {
    const lines: StatusDetailLine[] = [];
    const tracker = tokenTrackerRef.current;
    const liveUsage = liveContextUsageRef.current;
    const liveUsedPct = liveUsage
      ? Math.max(0, Math.min(100, liveUsage.usagePct * 100))
      : undefined;
    const liveContextRemaining = liveUsedPct !== undefined
      ? Math.max(0, Math.min(100, 100 - liveUsedPct))
      : undefined;
    const contextLine = buildContextProgressBar(
      liveContextRemaining ?? (tracker?.turnCount ? tracker.contextPercentRemaining : undefined),
    );
    if (contextLine) {
      if (compactedCountRef.current > 0) {
        contextLine.content += ` · compacted ${compactedCountRef.current}x`;
      }
      lines.push(contextLine);
    }
    // Per-component breakdown (when available from context_usage_breakdown event)
    if (liveUsage) {
      const parts = buildContextBreakdownSegments({
        systemPromptTokens: liveUsage.systemPromptTokens,
        conversationTokens: liveUsage.conversationTokens,
        skillsTokens: liveUsage.skillsTokens,
        toolSchemasTokens: liveUsage.toolSchemasTokens,
        mcpToolsTokens: liveUsage.mcpToolsTokens,
      });
      if (parts.length > 0) {
        lines.push({ segments: parts, emphasis: true });
      }
    }

    // Context window size guard — warn for small windows
    const contextWindow = liveUsage?.contextWindow ?? tracker?.contextWindow ?? 128_000;
    const guard = validateContextWindow(contextWindow);
    if (guard.level !== 'ok') {
      lines.push({ content: `CTX guard: ${guard.message}`, color: guard.level === 'error' ? 'red' : 'yellow' });
    }
    const mcpLines = buildMcpFooterLines(mcpStatusesRef.current);
    const mcpHealthy = mcpStatusesRef.current.length > 0
      && mcpStatusesRef.current.every((status) => status.state === 'ready' || status.state === 'degraded');
    if (!mcpHealthy) {
      lines.push(...mcpLines);
    } else if (lines.length === 0) {
      // keep one short line only if nothing else is shown
      lines.push(mcpLines[0]!);
    }
    return lines.slice(0, 3);
  }, [compactedVersion, contextUsageVersion, elapsedMs, isLoading, mcpStatusVersion, messages.length]);

  const spinnerTokenCount = useMemo(() => {
    if (!isLoading) return undefined;
    return estimateTurnTokenCount(runStatsRef.current, tokenTrackerRef.current);
  }, [elapsedMs, isLoading, messages.length, streamingContent, streamingThinking]);

  // Interrupt handler — cancels current agent run
  const handleInterrupt = useCallback(() => {
    agentRef.current?.interrupt('user_interrupt');
    if (abortRef.current) {
      abortRef.current.abort();
    }
    // Reset loading state so input stays responsive while agent winds down
    setIsLoading(false);
      clearStreamingRun('abort');
      setStreamingThinking(null);
      const toolSummary = buildToolLifecycleSummary(toolLifecycleStateRef.current);
      setSpinnerRunning(toolSummary.runningLine);
      setSpinnerStatus(toolSummary.statusLine);
    // Clear any pending dialog states (permission, questions, plan review)
    setPermissionRequest(undefined);
    permissionResolveRef.current?.(false);
    permissionResolveRef.current = null;
    setAskQuestions(null);
    askResolveRef.current?.({});
    askResolveRef.current = null;
    askRejectRef.current = null;
    setPlanReview(null);
    planReviewResolveRef.current?.('cancel');
    planReviewResolveRef.current = null;
    // Reset state machine to idle so input is enabled
    stateMachineRef.current?.transition({ type: 'turn_complete' });
    // Stop elapsed timer
    if (elapsedTimerRef.current) {
      clearInterval(elapsedTimerRef.current);
      elapsedTimerRef.current = null;
    }
    setElapsedMs(elapsedRef.current);
    runStatsRef.current = null;
  }, [clearStreamingRun, pushSpinnerDetail]);

  // Exit handler — clean shutdown (Ctrl+C double-tap or Ctrl+D)
  const handleExit = useCallback(() => {
    agentRef.current?.interrupt('process_exit');
    if (abortRef.current) abortRef.current.abort();
    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    process.exit(0);
  }, []);

  // AskUserQuestion submit handler
  const handleAskSubmit = useCallback(
    (answers: Record<string, string>) => {
      askResolveRef.current?.(answers);
      askResolveRef.current = null;
      askRejectRef.current = null;
      setAskQuestions(null);
      // Fire state machine transition: user answered the question
      stateMachineRef.current?.transition({ type: 'user_answer' });
    },
    [],
  );

  const handleAskCancel = useCallback(() => {
    askRejectRef.current?.(new Error('User cancelled'));
    askResolveRef.current = null;
    askRejectRef.current = null;
    setAskQuestions(null);
  }, []);

  // Plan review handlers
  const handlePlanReviewSubmit = useCallback(() => {
    const choice = (["proceed", "edit", "cancel"] as const)[planReviewIndex] ?? "cancel";
    planReviewResolveRef.current?.(choice);
    planReviewResolveRef.current = null;
    setPlanReview(null);
    // Fire state machine transition based on user's plan review decision
    if (choice === 'proceed') {
      stateMachineRef.current?.transition({ type: 'user_approve_plan' });
    } else {
      stateMachineRef.current?.transition({ type: 'user_reject_plan' });
    }
  }, [planReviewIndex]);

  const handlePlanReviewCancel = useCallback(() => {
    planReviewResolveRef.current?.("cancel");
    planReviewResolveRef.current = null;
    setPlanReview(null);
    // Fire state machine transition: user cancelled plan review
    stateMachineRef.current?.transition({ type: 'user_reject_plan' });
  }, []);

  useEffect(() => {
    if (messages.length === 0) {
      threadEventsRef.current = [];
      setThreadEvents([]);
      setCodexTaskSnapshots([]);
      setCodexTurnSnapshots([]);
    }
  }, [messages.length]);

  const askUserQuestion = askQuestions
    ? { questions: askQuestions, onSubmit: handleAskSubmit, onCancel: handleAskCancel }
    : undefined;

  return (
    <REPL
      messages={messages}
      threadEvents={threadEvents}
      codexTaskSnapshots={codexTaskSnapshots}
      codexTurnSnapshots={codexTurnSnapshots}
      presentationMode={options.presentationMode ?? 'codex'}
      isLoading={isLoading}
      streamingContent={streamingContent}
      streamingThinking={streamingThinking}
      streamingElapsedMs={elapsedMs}
      onSubmit={onSubmit}
      onInterrupt={handleInterrupt}
      onExit={handleExit}
      onViewportDebugEvent={(event) => {
        if (event.debugType === "manual_scroll") {
          emitDebugEvent({
            type: "viewport_manual_scroll",
            action: event.action ?? "scroll_by",
            delta: event.delta,
            targetTop: event.targetTop,
            timestamp: Date.now(),
          });
          return;
        }

        emitDebugEvent({
          type: "viewport_state",
          ...event,
          timestamp: Date.now(),
        });
      }}
      model={modelRef.current}
      statusSegments={statusSegments}
      statusDetailLines={statusDetailLines}
      commands={replCommands}
      askUserQuestion={askUserQuestion}
      planReview={planReview}
      planReviewIndex={planReviewIndex}
      onPlanReviewNavigate={(dir) => setPlanReviewIndex((i) => Math.max(0, Math.min(2, i + dir)))}
      onPlanReviewSubmit={handlePlanReviewSubmit}
      onPlanReviewCancel={handlePlanReviewCancel}
      spinnerTokenCount={spinnerTokenCount}
      spinnerVerb={spinnerVerb}
      spinnerStatus={spinnerStatus}
      spinnerDetails={spinnerDetails}
      spinnerRunning={spinnerRunning}
      spinnerCompleted={spinnerCompleted}
      agents={agentEntries}
      history={historyRef2.current}
      onHistoryAdd={handleHistoryAdd}
      modelSelectorOpen={modelSelectorOpen}
      modelSelectorCurrentModel={modelRef.current}
      modelSelectorCurrentEffort={reasoningEffortRef.current}
      modelSelectorKnownModels={getAllModels()}
      onModelSelect={handleModelSelect}
      onModelSelectorCancel={handleModelSelectorCancel}
      onModelEffortChange={handleModelEffortChange}
      effortSelectorOpen={effortSelectorOpen}
      effortSelectorCurrent={reasoningEffortRef.current}
      effortSelectorLevels={JARVIS_REASONING_EFFORTS}
      onEffortSelect={handleEffortSelect}
      onEffortSelectorCancel={handleEffortSelectorCancel}
      helpPopupOpen={helpPopupOpen}
      helpPopupCommands={SLASH_COMMANDS.map((c) => ({ name: c.name, description: c.description }))}
      onHelpPopupClose={() => setHelpPopupOpen(false)}
      permissionMode={permissionModeRef.current}
      onPermissionModeCycle={handlePermissionModeCycle}
      permissionRequest={permissionRequest}
      fileEntries={fileEntries}
      onFileSearch={handleFileSearch}
      welcome={<WelcomeScreen appName="Jarvis" subtitle="AI Coding Assistant" model={parseModelName(modelRef.current).cleanName} color="#00BFFF" tips={['Send a prompt to begin', '/help for commands', 'Ctrl+C twice exits']} />}
    />
  );
}

