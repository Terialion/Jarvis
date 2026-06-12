import {
  Box,
  Text,
  type Key,
  useApp,
  useHasSelection,
  useInput,
  useSelection,
  type ScrollBoxHandle,
} from "../ink-renderer/index.js";
import { AgentsPanel, type AgentStatusEntry } from "./AgentsPanel";
import React from "react";
import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { AskUserQuestion } from "./AskUserQuestion";
import { PlanReview } from "./PlanReview";
import type { AskQuestionDef } from "@jarvis/tools";
import type { ThreadEvent, ModelInfo } from "@jarvis/agent";
import { buildCodexTranscriptItems } from "../../presentation/CodexTimeline.js";
import { HelpPopup, type HelpCommandEntry } from "./HelpPopup";
import { ShellTextPanel } from "./ShellTextPanel";
import {
  buildCodexTimelineState,
  buildSearchExcerpt,
  type CodexTaskSnapshot,
  type CodexTurnSnapshot,
} from "../../presentation/codex-timeline-state.js";
import { Divider } from "./Divider";
import {
  type Message,
  isStandaloneRunningToolMessage,
  LiveAssistantAnswerRail,
  LiveAssistantReasoningRail,
  LiveToolUseRail,
  MessageList,
} from "./MessageList";
import { ModelSelector, type ModelSelectionResult } from "./ModelSelector";
import type { ModelSelectorProps } from "./ModelSelector";
import { EffortSelector } from "./EffortSelector";
import type { EffortSelectorProps } from "./EffortSelector";
import { type PermissionAction, PermissionRequest } from "./PermissionRequest";
import { PromptInput } from "./PromptInput";
import { computeMatches, SearchOverlay } from "./SearchOverlay";
import { Spinner } from "./Spinner";
import { StatusLine, type StatusLineSegment } from "./StatusLine";
import type { SearchMatch } from "./SearchOverlay";
import type { TuiPresentationMode } from "../../presentation/contracts.js";
import { useRegisterKeybindingContext } from "./keybindings/KeybindingContext";
import { useKeybindings } from "./keybindings/useKeybinding";
import {
  shouldAutoScrollToBottomOnContentUpdate,
  shouldResumeLiveOutputFromBottomAction,
} from "./viewport-mode.js";
import { buildViewportFooterView } from "./viewport-footer.js";
import { FullscreenLayout } from "./FullscreenLayout.js";
import {
  useSetBottomFloat,
  useSetBottomReplacement,
  useSetPromptModal,
  useSetPromptOverlay,
} from "./PromptOverlayContext.js";
import { TranscriptViewport, type TranscriptItem } from "./TranscriptViewport.js";
import { createViewportState, reduceViewportState } from "./viewport-controller.js";
import { ViewportProvider, useViewportContext } from "./ViewportContext.js";
import { useCopyOnSelect } from "./useCopyOnSelect.js";

type REPLCommand = {
  name: string;
  description: string;
  onExecute: (args: string, fullInput: string) => void;
};

export type StatusDetailLine = {
  content?: string;
  color?: "green" | "yellow" | "red" | "cyan" | "gray";
  emphasis?: boolean;
  segments?: StatusLineSegment[];
};

type PermissionRequestState = {
  toolName: string;
  description: string;
  details?: string;
  patternLabel?: string;
  preview?: React.ReactNode;
  onDecision: (action: PermissionAction) => void;
};

type AskUserQuestionState = {
  questions: AskQuestionDef[];
  onSubmit: (answers: Record<string, string>) => void;
  onCancel: () => void;
};

export type REPLProps = {
  onSubmit: (message: string) => Promise<void> | void;
  onExit?: () => void;
  /** Called when user requests interrupt (Esc while loading, or first Ctrl+C). */
  onInterrupt?: () => void;
  onViewportDebugEvent?: (event: {
    mode: "following" | "history" | "selection";
    followOutput: boolean;
    hasSelection: boolean;
    interactivePromptActive: boolean;
    isLoading: boolean;
    scrollTop: number;
    scrollHeight: number;
    viewportHeight: number;
    pendingScrollDelta: number;
    remainingScrollDistance: number;
    clampMin?: number;
    clampMax?: number;
    transcriptTotalHeight?: number;
    transcriptRangeStart?: number;
    transcriptRangeEnd?: number;
  }) => void;

  messages: Message[];
  isLoading?: boolean;
  streamingContent?: string | null;
  streamingThinking?: string | null;
  streamingElapsedMs?: number;
  threadEvents?: ThreadEvent[];
  codexTaskSnapshots?: CodexTaskSnapshot[];
  codexTurnSnapshots?: CodexTurnSnapshot[];
  presentationMode?: TuiPresentationMode;

  welcome?: React.ReactNode;

  permissionRequest?: PermissionRequestState;
  askUserQuestion?: AskUserQuestionState;

  // Plan review (CC-style exit_plan_mode popup)
  planReview?: import("@jarvis/tools").PlanReviewRequest | null;
  planReviewIndex?: number;
  onPlanReviewNavigate?: (dir: number) => void;
  onPlanReviewSubmit?: () => void;
  onPlanReviewCancel?: () => void;

  // Permission mode cycling (Shift+Tab)
  permissionMode?: string;
  onPermissionModeCycle?: () => void;

  commands?: REPLCommand[];
  model?: string;
  statusSegments?: StatusLineSegment[];
  statusDetailLines?: StatusDetailLine[];

  // Model selector
  modelSelectorOpen?: boolean;
  modelSelectorCurrentModel?: string;
  modelSelectorCurrentEffort?: string;
  modelSelectorKnownModels?: ModelInfo[];
  onModelSelect?: (result: ModelSelectionResult) => void;
  onModelSelectorCancel?: () => void;
  onModelEffortChange?: (effort: string) => void;

  // Effort selector
  effortSelectorOpen?: boolean;
  effortSelectorCurrent?: string;
  effortSelectorLevels?: readonly string[];
  onEffortSelect?: (effort: string) => void;
  onEffortSelectorCancel?: () => void;
  onEffortSelectorChange?: (effort: string) => void;

  // Help popup
  helpPopupOpen?: boolean;
  helpPopupCommands?: HelpCommandEntry[];
  onHelpPopupClose?: () => void;
  contextPanel?: { title: string; subtitle?: string; lines: string[] } | null;
  onContextPanelClose?: () => void;
  mcpPanel?: { title: string; subtitle?: string; lines: string[] } | null;
  onMcpPanelClose?: () => void;

  prefix?: string;
  placeholder?: string;
  history?: string[];
  /** Called when a prompt is submitted - parent can persist to disk */
  onHistoryAdd?: (entry: string) => void;

  renderMessage?: (message: Message) => React.ReactNode;
  spinner?: React.ReactNode;
  spinnerTokenCount?: number;
  spinnerVerb?: string;
  spinnerStatus?: string;
  spinnerDetails?: string[];
  spinnerRunning?: string;
  spinnerCompleted?: string[];

  // Agent panel (Ctrl+A)
  agents?: AgentStatusEntry[];

  // @ file reference
  fileEntries?: import("./utils/fileScanner").FileEntry[];
  onFileSearch?: (query: string) => void;
};

export function REPL({
  onSubmit,
  onExit,
  onInterrupt,
  onViewportDebugEvent,
  messages,
  isLoading = false,
  streamingContent,
  streamingThinking,
  streamingElapsedMs,
  threadEvents = [],
  codexTaskSnapshots = [],
  codexTurnSnapshots = [],
  presentationMode = "claude",
  welcome,
  permissionRequest,
  askUserQuestion,
  planReview,
  planReviewIndex = 0,
  onPlanReviewNavigate,
  onPlanReviewSubmit,
  onPlanReviewCancel,
  permissionMode,
  onPermissionModeCycle,
  commands = [],
  model,
  statusSegments,
  statusDetailLines = [],
  prefix = "\u276F",
  placeholder,
  history: externalHistory,
  onHistoryAdd,
  renderMessage,
  spinner,
  spinnerTokenCount,
  spinnerVerb,
  spinnerStatus,
  spinnerDetails,
  spinnerRunning,
  spinnerCompleted,
  agents,
  // @ file reference
  fileEntries,
  onFileSearch,
  // Model selector
  modelSelectorOpen = false,
  modelSelectorCurrentModel = "",
  modelSelectorCurrentEffort = "high",
  modelSelectorKnownModels = [],
  onModelSelect,
  onModelSelectorCancel,
  onModelEffortChange,
  // Effort selector
  effortSelectorOpen = false,
  effortSelectorCurrent = "high",
  effortSelectorLevels = [],
  onEffortSelect,
  onEffortSelectorCancel,
  onEffortSelectorChange,
  // Help popup
  helpPopupOpen = false,
  helpPopupCommands = [],
  onHelpPopupClose,
  contextPanel = null,
  onContextPanelClose,
  mcpPanel = null,
  onMcpPanelClose,
}: REPLProps): React.ReactNode {
  const { exit } = useApp();
  const scrollRef = useRef<ScrollBoxHandle | null>(null);
  const transcriptMetricsRef = useRef<{
    clampMin?: number;
    clampMax?: number;
    totalHeight: number;
    startIndex: number;
    endIndex: number;
  } | null>(null);
  const [inputValue, setInputValue] = useState("");
  const [showAgents, setShowAgents] = useState(false);
  // Auto-show agents panel when agents are active, hide when all done
  const agentsActive = (agents?.length ?? 0) > 0;
  const agentsPanelVisible = showAgents || agentsActive;
  const [agentsFocused, setAgentsFocused] = useState(false);
  const [internalHistory, setInternalHistory] = useState<string[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchMatch, setActiveSearchMatch] = useState<SearchMatch | null>(null);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const [toolResultsExpanded, setToolResultsExpanded] = useState(false);
  const [viewportState, dispatchViewport] = useReducer(reduceViewportState, undefined, createViewportState);
  const [showExitHint, setShowExitHint] = useState(false);
  const exitHintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollDrainTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const submittingRef = useRef(false);
  const lastViewportDebugRef = useRef<string>("");
  const hasSelection = useHasSelection();
  const { clearSelection, copySelectionNoClear, shiftSelection, captureScrolledRows } = useSelection();

  const history = externalHistory ?? internalHistory;
  const interactivePromptActive = !!askUserQuestion || !!permissionRequest || !!planReview;
  const followOutput = viewportState.followOutput;
  const scrollPositionKind = viewportState.mode;
  const overlaysOpen =
    searchOpen || modelSelectorOpen || effortSelectorOpen || helpPopupOpen || !!contextPanel || !!mcpPanel;
  const viewportHotkeysActive = !overlaysOpen && !agentsFocused;

  useRegisterKeybindingContext("Chat", !overlaysOpen && !interactivePromptActive);
  useRegisterKeybindingContext("Scroll", viewportHotkeysActive);

  const stopFollowingOutput = useCallback(
    (kind: "history" | "selection" = "history") => {
      if (kind === "selection") {
        dispatchViewport({ type: "selection_changed", hasSelection: true });
        return;
      }
      dispatchViewport({ type: "user_scrolled" });
    },
    [],
  );

  const getEffectiveViewportTop = useCallback((handle: ScrollBoxHandle) => {
    const maxScroll = Math.max(0, handle.getScrollHeight() - handle.getViewportHeight());
    if (followOutput || handle.isSticky()) return maxScroll;
    return Math.max(0, Math.min(maxScroll, handle.getScrollTop() + handle.getPendingDelta()));
  }, [followOutput]);

  const getRemainingScrollDistance = useCallback(() => {
    const handle = scrollRef.current;
    if (!handle) return Number.POSITIVE_INFINITY;
    return Math.max(0, handle.getScrollHeight() - handle.getViewportHeight() - getEffectiveViewportTop(handle));
  }, [getEffectiveViewportTop]);

  const resumeFollowingOutput = useCallback(() => {
    scrollRef.current?.scrollToBottom();
    dispatchViewport({ type: "resume_follow" });
  }, []);

  const handleViewportBottomAction = useCallback(() => {
    if (!shouldResumeLiveOutputFromBottomAction(hasSelection)) {
      scrollRef.current?.scrollToBottom();
      dispatchViewport({ type: "bottom_action" });
      return;
    }

    dispatchViewport({ type: "bottom_action" });
    resumeFollowingOutput();
  }, [hasSelection, resumeFollowingOutput]);

  const handleViewportScrollBy = useCallback(
    (dy: number) => {
      const handle = scrollRef.current;
      if (!handle || dy === 0) return;
      const maxScroll = Math.max(0, handle.getScrollHeight() - handle.getViewportHeight());
      const currentTop = getEffectiveViewportTop(handle);
      const targetTop = Math.max(0, Math.min(maxScroll, currentTop + dy));
      const actualDelta = targetTop - currentTop;

      // Shift text selection to track the scrolled content
      if (hasSelection && actualDelta !== 0) {
        const maxRow = process.stdout.rows ?? 40;
        // Capture rows scrolling out of view so they remain copyable
        if (actualDelta > 0) {
          // Content moves up: rows at the top scroll out
          captureScrolledRows(0, actualDelta - 1, "above");
        } else {
          // Content moves down: rows at the bottom scroll out
          captureScrolledRows(maxRow + actualDelta, maxRow - 1, "below");
        }
        // Shift selection: content at row R moves to row R-dy
        shiftSelection(-actualDelta, 0, maxRow);
      }
      handle.scrollTo(targetTop);
      const nextKind = hasSelection ? "selection" : "history";
      stopFollowingOutput(nextKind);
    },
    [captureScrolledRows, getEffectiveViewportTop, hasSelection, shiftSelection, stopFollowingOutput],
  );

  const handleViewportScrollToTop = useCallback(() => {
    scrollRef.current?.scrollTo(0);
    stopFollowingOutput(hasSelection ? "selection" : "history");
  }, [hasSelection, stopFollowingOutput]);

  // Cleanup timers on unmount
  useEffect(
    () => () => {
      if (exitHintTimerRef.current) clearTimeout(exitHintTimerRef.current);
      if (scrollDrainTimerRef.current) clearTimeout(scrollDrainTimerRef.current);
    },
    [],
  );

  // Detect user-initiated scrolls (mouse wheel, trackpad) and break followOutput
  useEffect(() => {
    const handle = scrollRef.current;
    if (!handle) return;
    return handle.subscribe(() => {
      // After any imperative scroll, check if we're still at the bottom
      const remaining = Math.max(
        0,
        handle.getScrollHeight() - handle.getViewportHeight() - getEffectiveViewportTop(handle),
      );
      if (remaining > 3 && followOutput) {
        stopFollowingOutput(hasSelection ? "selection" : "history");
      }
      dispatchViewport({ type: "scroll_draining_changed", scrollDraining: true });
      if (scrollDrainTimerRef.current) clearTimeout(scrollDrainTimerRef.current);
      scrollDrainTimerRef.current = setTimeout(() => {
        dispatchViewport({ type: "scroll_draining_changed", scrollDraining: false });
      }, 150);
    });
  }, [followOutput, getEffectiveViewportTop, hasSelection, stopFollowingOutput]);

  useEffect(() => {
    dispatchViewport({ type: "selection_changed", hasSelection });
  }, [hasSelection]);

  useEffect(() => {
    dispatchViewport({ type: "interactive_prompt_changed", interactivePromptActive });
  }, [interactivePromptActive]);

  useKeybindings(
    {
      "scroll:pageUp": () => {
        const amount = Math.max(1, Math.floor((scrollRef.current?.getViewportHeight() ?? 20) * 0.85));
        handleViewportScrollBy(-amount);
      },
      "scroll:pageDown": () => {
        const amount = Math.max(1, Math.floor((scrollRef.current?.getViewportHeight() ?? 20) * 0.85));
        handleViewportScrollBy(amount);
      },
      "scroll:lineUp": () => {
        handleViewportScrollBy(-3);
      },
      "scroll:lineDown": () => {
        handleViewportScrollBy(3);
      },
      "scroll:top": () => {
        handleViewportScrollToTop();
      },
      "scroll:bottom": () => {
        handleViewportBottomAction();
      },
      "selection:copy": () => {
        if (!hasSelection) return false;
        copySelectionNoClear();
      },
    },
    { context: "Scroll", isActive: viewportHotkeysActive },
  );

  const messageContents = messages.map((m) =>
    typeof m.content === "string"
      ? m.content
      : m.content.map((b) => ("text" in b ? b.text : "")).join(" "),
  );

  const promptCommands = commands.map((c) => ({
    name: c.name,
    description: c.description,
  }));

  const handleSubmit = useCallback(
    (value: string) => {
      if (submittingRef.current) return;

      const trimmed = value.trim();
      if (!trimmed) return;

      if (trimmed.startsWith("/")) {
        const spaceIndex = trimmed.indexOf(" ");
        const cmdName = spaceIndex >= 0 ? trimmed.slice(1, spaceIndex) : trimmed.slice(1);
        const cmdArgs = spaceIndex >= 0 ? trimmed.slice(spaceIndex + 1).trim() : "";

        const cmd = commands.find((c) => c.name === cmdName);
        if (cmd) {
          setInputValue("");
          // Save to history before executing (slash commands were bypassing history)
          if (!externalHistory) {
            setInternalHistory((prev) => [trimmed, ...prev]);
          } else {
            onHistoryAdd?.(trimmed);
          }
          cmd.onExecute(cmdArgs, trimmed);
          return;
        }
      }

      submittingRef.current = true;
      setInputValue("");
      if (!externalHistory) {
        setInternalHistory((prev) => [trimmed, ...prev]);
      } else {
        onHistoryAdd?.(trimmed);
      }

      const result = onSubmit(trimmed);
      if (result && typeof result.then === "function") {
        result.finally(() => {
          submittingRef.current = false;
        });
      } else {
        submittingRef.current = false;
      }
    },
    [commands, onSubmit, externalHistory],
  );

  const lastCtrlCPressRef = useRef(0);

  useInput(
    (_input: string, key: Key) => {
      if (viewportHotkeysActive) {
        if (key.pageUp) {
          const amount = Math.max(1, Math.floor((scrollRef.current?.getViewportHeight() ?? 20) * 0.85));
          handleViewportScrollBy(-amount);
          return;
        }
        if (key.pageDown) {
          const amount = Math.max(1, Math.floor((scrollRef.current?.getViewportHeight() ?? 20) * 0.85));
          handleViewportScrollBy(amount);
          return;
        }
        if (key.ctrl && key.home) {
          handleViewportScrollToTop();
          return;
        }
        if (key.end || (key.ctrl && key.end)) {
          handleViewportBottomAction();
          return;
        }
      }

      if (hasSelection && key.escape) {
        clearSelection();
        return;
      }
      if (hasSelection && key.ctrl && _input === "c") {
        lastCtrlCPressRef.current = 0;
        copySelectionNoClear();
        return;
      }
      if (askUserQuestion || permissionRequest) {
        return;
      }
      // Agents panel focus mode 閳?route keys to panel
      if (agentsFocused && agentsPanelVisible) {
        if (_input === "q" || key.escape || (key.ctrl && _input === "g")) {
          setAgentsFocused(false);
          return;
        }
        // j/up/down/k are handled by the AgentsPanel internally via useInput
        // The AgentsPanel component listens for these keys when focused
        return;
      }

      // Ctrl+G: toggle agents panel focus when agents are visible
      if (key.ctrl && _input === "g") {
        if (agentsPanelVisible) {
          setAgentsFocused((prev) => !prev);
        } else {
          setShowAgents((prev) => !prev);
        }
        return;
      }

      // Plan review: j/k/enter/escape navigation
      if (planReview) {
        if (_input === "j" || key.downArrow) { onPlanReviewNavigate?.(1); return; }
        if (_input === "k" || key.upArrow) { onPlanReviewNavigate?.(-1); return; }
        if (key.return) { onPlanReviewSubmit?.(); return; }
        if (key.escape) { onPlanReviewCancel?.(); return; }
        return;
      }

      // Ctrl+C: first press interrupts/clears, second within 1s exits (like Codex)
      if (key.ctrl && _input === "c") {
        const now = Date.now();
        if (lastCtrlCPressRef.current > 0 && now - lastCtrlCPressRef.current < 1000) {
          lastCtrlCPressRef.current = 0;
          setShowExitHint(false);
          if (exitHintTimerRef.current) { clearTimeout(exitHintTimerRef.current); exitHintTimerRef.current = null; }
          if (onExit) { onExit(); } else { exit(); }
          return;
        }
        lastCtrlCPressRef.current = now;
        // Show exit hint for 1 second
        setShowExitHint(true);
        if (exitHintTimerRef.current) clearTimeout(exitHintTimerRef.current);
        exitHintTimerRef.current = setTimeout(() => {
          setShowExitHint(false);
          exitHintTimerRef.current = null;
        }, 1000);
        if (isLoading && onInterrupt) {
          onInterrupt();
        } else {
          // When not loading, clear the input so user can type a new command
          setInputValue("");
        }
        return;
      }
      // Esc: interrupt while loading (like Codex bottom pane)
      if (key.escape && isLoading) {
        onInterrupt?.();
        return;
      }
      // Any other key resets the double-press timer and clears exit hint
      lastCtrlCPressRef.current = 0;
      if (showExitHint) {
        setShowExitHint(false);
        if (exitHintTimerRef.current) { clearTimeout(exitHintTimerRef.current); exitHintTimerRef.current = null; }
      }

      if (key.ctrl && _input === "d") {
        if (onExit) {
          onExit();
        } else {
          exit();
        }
      }
      if (key.ctrl && _input === "f") {
        setSearchOpen(true);
      }
      if (key.ctrl && _input === "t") {
        if (presentationMode === "codex") {
          setToolResultsExpanded((prev) => !prev);
        } else {
          setThinkingExpanded((prev) => !prev);
        }
      }
      // Ctrl+G handled earlier for focus/panel toggle 閳?skip here
      if (key.ctrl && _input === "o") {
        setToolResultsExpanded((prev) => !prev);
      }
      // Shift+Tab: cycle permission modes (suggest 閳?auto-edit 閳?full-auto 閳?suggest)
      if (key.tab && key.shift) {
        onPermissionModeCycle?.();
      }
    },
    // Deactivate when search, model, or effort selector overlays are open
    { isActive: !overlaysOpen },
  );

  const resolvedSegments = statusSegments ?? buildDefaultSegments(model);
  const showWelcome = welcome && messages.length === 0 && threadEvents.length === 0 && !isLoading;
  const showPermission = !!permissionRequest;
  const messageAreaFlexGrow = showWelcome ? 0 : 1;
  const contentAreaFlexGrow = showWelcome ? 0 : 1;
  const codexState = useMemo(
    () =>
      buildCodexTimelineState({
        events: threadEvents,
        liveStatus: {
          isLoading,
          elapsedMs: streamingElapsedMs,
          tokenCount: spinnerTokenCount,
          verb: spinnerVerb,
          status: spinnerStatus,
          details: spinnerDetails,
          running: spinnerRunning,
          completed: spinnerCompleted,
        },
        messages: messages
          .filter((message) => message.role === "user" || message.role === "assistant" || message.role === "system")
          .map((message) => ({
            id: message.id,
            role: message.role,
            text:
              typeof message.content === "string"
                ? message.content
                : message.content
                    .map((block) => ("text" in block ? block.text : ""))
                    .join("\n"),
          })),
        taskSnapshots: codexTaskSnapshots,
        turnSnapshots: codexTurnSnapshots,
      }),
    [
      codexTaskSnapshots,
      codexTurnSnapshots,
      isLoading,
      messages,
      spinnerCompleted,
      spinnerDetails,
      spinnerRunning,
      spinnerStatus,
      spinnerTokenCount,
      spinnerVerb,
      streamingElapsedMs,
      threadEvents,
    ],
  );
  const searchContents =
    presentationMode === "codex"
      ? codexState.searchDocuments.map((document) => document.text)
      : messageContents;
  const codexSearchState = useMemo(() => {
    if (presentationMode !== "codex" || !searchQuery || !activeSearchMatch) {
      return undefined;
    }
    const doc = codexState.searchDocuments[activeSearchMatch.index];
    if (!doc) return undefined;
    return {
      query: searchQuery,
      activeDocumentId: doc.id,
      activeExcerpt: buildSearchExcerpt(doc.text, searchQuery),
    };
  }, [activeSearchMatch, codexState.searchDocuments, presentationMode, searchQuery]);

  const finalViewportStatusLine = useMemo(
    (): StatusDetailLine | null => buildViewportFooterView({ mode: scrollPositionKind, isLoading }),
    [isLoading, scrollPositionKind],
  );

  const combinedStatusDetailLines = useMemo(
    () => (finalViewportStatusLine ? [finalViewportStatusLine, ...statusDetailLines] : statusDetailLines),
    [finalViewportStatusLine, statusDetailLines],
  );

  const bottomReplacementNode = useMemo(() => {
    if (!askUserQuestion && !showPermission && !planReview) {
      return null;
    }

    return (
      <ReplBottomReplacement
        askUserQuestion={askUserQuestion}
        permissionRequest={showPermission ? permissionRequest : undefined}
        planReview={planReview}
        planReviewIndex={planReviewIndex}
      />
    );
  }, [askUserQuestion, permissionRequest, planReview, planReviewIndex, showPermission]);

  const transcriptItems = useMemo<TranscriptItem[]>(() => {
    const items: TranscriptItem[] = [];

    if (showWelcome && welcome) {
      items.push({
        id: "welcome",
        estimatedHeight: 14,
        render: () => <Box marginBottom={0}>{welcome}</Box>,
      });
    }

    if (presentationMode === "codex") {
      return buildCodexTranscriptItems({
        state: codexState,
        search: codexSearchState,
        detailsExpanded: toolResultsExpanded,
        welcome: showWelcome ? welcome : undefined,
      });
    } else {
      const liveToolMessages = messages.filter((message) => isStandaloneRunningToolMessage(message));

      items.push({
        id: "message-list",
        estimatedHeight: Math.max(12, messages.length * 6),
        render: () => (
          <MessageList
            messages={messages}
            renderMessage={renderMessage}
            allThinkingExpanded={thinkingExpanded}
            allToolResultsExpanded={toolResultsExpanded}
            searchQuery={searchQuery}
            activeSearchMatch={activeSearchMatch}
          />
        ),
      });

      for (const message of liveToolMessages) {
        items.push({
          id: `live-tool-${message.id}`,
          estimatedHeight: 10,
          render: () => (
            <LiveToolUseRail
              message={message}
              allToolResultsExpanded={toolResultsExpanded}
            />
          ),
        });
      }

      if (streamingThinking && streamingThinking.trim()) {
        items.push({
          id: "live-reasoning",
          estimatedHeight: thinkingExpanded ? 12 : 8,
          render: () => (
            <LiveAssistantReasoningRail
              text={streamingThinking}
              elapsedMs={streamingElapsedMs}
              expanded={thinkingExpanded}
            />
          ),
        });
      }

      if (streamingContent && streamingContent.trim()) {
        items.push({
          id: "live-answer",
          estimatedHeight: Math.max(6, streamingContent.split("\n").length + 3),
          render: () => <LiveAssistantAnswerRail text={streamingContent} />,
        });
      }

      if (isLoading && !streamingContent && !streamingThinking) {
        items.push({
          id: "spinner",
          estimatedHeight: 5,
          render: () => (
            <Box marginTop={messages.length > 0 ? 1 : 0}>
              {spinner ?? (
                <Spinner
                  tokenCount={spinnerTokenCount}
                  verb={spinnerVerb}
                  status={spinnerStatus}
                  details={spinnerDetails}
                  running={spinnerRunning}
                  completed={spinnerCompleted}
                />
              )}
            </Box>
          ),
        });
      }
    }

    return items;
  }, [
    activeSearchMatch,
    codexSearchState,
    codexState,
    isLoading,
    messages,
    presentationMode,
    renderMessage,
    searchQuery,
    showWelcome,
    spinner,
    spinnerCompleted,
    spinnerDetails,
    spinnerRunning,
    spinnerStatus,
    spinnerTokenCount,
    spinnerVerb,
    streamingContent,
    streamingElapsedMs,
    streamingThinking,
    thinkingExpanded,
    toolResultsExpanded,
    welcome,
  ]);

  const overlayNode = useMemo(
    () => (
      <ReplOverlaySurface
        searchOpen={searchOpen}
        setSearchOpen={setSearchOpen}
        searchContents={searchContents}
        setActiveSearchMatch={setActiveSearchMatch}
        setSearchQuery={setSearchQuery}
        agents={agents}
        agentsPanelVisible={agentsPanelVisible}
        agentsFocused={agentsFocused}
        onCloseAgents={() => {
          setShowAgents(false);
          setAgentsFocused(false);
        }}
      />
    ),
    [agents, agentsFocused, agentsPanelVisible, searchContents, searchOpen],
  );

  const modalNode = useMemo(
    () => (
      <ReplModalSurface
        modelSelectorOpen={modelSelectorOpen}
        modelSelectorKnownModels={modelSelectorKnownModels}
        modelSelectorCurrentModel={modelSelectorCurrentModel}
        modelSelectorCurrentEffort={modelSelectorCurrentEffort}
        effortSelectorLevels={effortSelectorLevels}
        onModelSelect={onModelSelect}
        onModelSelectorCancel={onModelSelectorCancel}
        onModelEffortChange={onModelEffortChange}
        effortSelectorOpen={effortSelectorOpen}
        effortSelectorCurrent={effortSelectorCurrent}
        onEffortSelect={onEffortSelect}
        onEffortSelectorCancel={onEffortSelectorCancel}
        onEffortSelectorChange={onEffortSelectorChange}
        helpPopupOpen={helpPopupOpen}
        helpPopupCommands={helpPopupCommands}
        onHelpPopupClose={onHelpPopupClose}
        contextPanel={contextPanel}
        onContextPanelClose={onContextPanelClose}
        mcpPanel={mcpPanel}
        onMcpPanelClose={onMcpPanelClose}
      />
    ),
    [
      contextPanel,
      effortSelectorCurrent,
      effortSelectorLevels,
      effortSelectorOpen,
      helpPopupCommands,
      helpPopupOpen,
      mcpPanel,
      modelSelectorCurrentEffort,
      modelSelectorCurrentModel,
      modelSelectorKnownModels,
      modelSelectorOpen,
      onContextPanelClose,
      onEffortSelect,
      onEffortSelectorCancel,
      onEffortSelectorChange,
      onHelpPopupClose,
      onMcpPanelClose,
      onModelEffortChange,
      onModelSelect,
      onModelSelectorCancel,
    ],
  );

  const viewportContextValue = {
    ...viewportState,
    dispatch: dispatchViewport,
    stopFollowingOutput,
    resumeFollowingOutput,
    handleBottomAction: handleViewportBottomAction,
  };

  // Manual scroll-to-bottom: only when followOutput is true (user hasn't scrolled up)
  // Replaces stickyScroll which was resetting scroll position to top on content change
  useEffect(() => {
    if (
      shouldAutoScrollToBottomOnContentUpdate({
        followOutput,
        hasSelection,
        interactivePromptActive,
        scrollDraining: viewportState.scrollDraining,
        remainingScrollDistance: getRemainingScrollDistance(),
      })
    ) {
      scrollRef.current?.scrollToBottom();
    }
  }, [
    streamingContent,
    messages.length,
    followOutput,
    getRemainingScrollDistance,
    hasSelection,
    interactivePromptActive,
    viewportState.scrollDraining,
  ]);

  useEffect(() => {
    if (!onViewportDebugEvent) return;
    const handle = scrollRef.current;
    const remainingScrollDistance = getRemainingScrollDistance();
    const payload = {
      mode: scrollPositionKind,
      followOutput,
      hasSelection,
      interactivePromptActive,
      isLoading,
      scrollTop: handle?.getScrollTop() ?? 0,
      scrollHeight: handle?.getScrollHeight() ?? 0,
      viewportHeight: handle?.getViewportHeight() ?? 0,
      pendingScrollDelta: handle?.getPendingDelta() ?? 0,
      remainingScrollDistance,
      clampMin: transcriptMetricsRef.current?.clampMin,
      clampMax: transcriptMetricsRef.current?.clampMax,
      transcriptTotalHeight: transcriptMetricsRef.current?.totalHeight,
      transcriptRangeStart: transcriptMetricsRef.current?.startIndex,
      transcriptRangeEnd: transcriptMetricsRef.current?.endIndex,
    };
    const snapshotKey = JSON.stringify(payload);
    if (snapshotKey === lastViewportDebugRef.current) return;
    lastViewportDebugRef.current = snapshotKey;
    onViewportDebugEvent(payload);
  }, [
    followOutput,
    getRemainingScrollDistance,
    hasSelection,
    interactivePromptActive,
    isLoading,
    messages.length,
    onViewportDebugEvent,
    scrollPositionKind,
    streamingContent,
    threadEvents.length,
  ]);

  return (
    <ViewportProvider value={viewportContextValue}>
      <FullscreenLayout
        scrollable={
          <TranscriptViewport
            items={transcriptItems}
            scrollRef={scrollRef}
            selectionLocked={hasSelection}
            followDisabled={!followOutput || viewportState.scrollDraining || interactivePromptActive}
            onMetricsChange={(metrics) => {
              transcriptMetricsRef.current = {
                clampMin: metrics.clampMin,
                clampMax: metrics.clampMax,
                totalHeight: metrics.totalHeight,
                startIndex: metrics.startIndex,
                endIndex: metrics.endIndex,
              };
            }}
          />
        }
        bottom={
          <ReplBottomShell
            inputValue={inputValue}
            setInputValue={setInputValue}
            handleSubmit={handleSubmit}
            prefix={prefix}
            placeholder={placeholder}
            overlaysOpen={overlaysOpen}
            isLoading={isLoading}
            promptCommands={promptCommands}
            history={history}
            fileEntries={fileEntries}
            onFileSearch={onFileSearch}
            showExitHint={showExitHint}
            resolvedSegments={resolvedSegments}
            combinedStatusDetailLines={combinedStatusDetailLines}
          />
        }
      >
        <ReplOverlayRegistrations
          overlayNode={overlayNode}
          modalNode={modalNode}
          bottomReplacementNode={bottomReplacementNode}
        />
      </FullscreenLayout>
    </ViewportProvider>
  );
}

function buildDefaultSegments(model?: string): StatusLineSegment[] {
  if (!model) return [];
  return [{ content: model, color: "green" }];
}

function ReplOverlayRegistrations({
  overlayNode,
  modalNode,
  bottomReplacementNode,
}: {
  overlayNode: React.ReactNode;
  modalNode: React.ReactNode;
  bottomReplacementNode: React.ReactNode;
}): React.ReactNode {
  useSetPromptOverlay(overlayNode);
  useSetPromptModal(modalNode);
  useSetBottomReplacement(bottomReplacementNode);
  useSetBottomFloat(null);
  return null;
}

function ReplBottomShell({
  inputValue,
  setInputValue,
  handleSubmit,
  prefix,
  placeholder,
  overlaysOpen,
  isLoading,
  promptCommands,
  history,
  fileEntries,
  onFileSearch,
  showExitHint,
  resolvedSegments,
  combinedStatusDetailLines,
}: {
  inputValue: string;
  setInputValue: (value: string) => void;
  handleSubmit: (value: string) => void | Promise<void>;
  prefix: string;
  placeholder?: string;
  overlaysOpen: boolean;
  isLoading: boolean;
  promptCommands: Array<{ name: string; description: string }>;
  history: string[];
  fileEntries?: import("./utils/fileScanner").FileEntry[];
  onFileSearch?: (query: string) => void;
  showExitHint: boolean;
  resolvedSegments: StatusLineSegment[];
  combinedStatusDetailLines: StatusDetailLine[];
}): React.ReactNode {
  const viewport = useViewportContext();
  const footerLine: StatusDetailLine | null = useMemo(
    () => {
      const footer = buildViewportFooterView({ mode: viewport.mode, isLoading });
      if (!footer) {
        return null;
      }

      return {
        emphasis: true,
        segments: footer.segments,
      };
    },
    [isLoading, viewport.mode],
  );
  const footerLines = useMemo(
    () => (footerLine ? [footerLine, ...combinedStatusDetailLines.slice(1)] : combinedStatusDetailLines.slice(1)),
    [combinedStatusDetailLines, footerLine],
  );

  return (
    <>
      <Divider />
      <Box flexDirection="column" minHeight={1} flexShrink={0}>
        <PromptInput
          value={inputValue}
          onChange={setInputValue}
          onSubmit={(value) => {
            void handleSubmit(value);
          }}
          prefix={prefix}
          placeholder={placeholder}
          disabled={overlaysOpen}
          isLoading={isLoading}
          commands={promptCommands}
          history={history}
          fileEntries={fileEntries}
          onFileSearch={onFileSearch}
        />
      </Box>

      <Divider />
      {showExitHint ? (
        <Box paddingX={1} flexShrink={0}>
          <Text color="yellow" bold>Press Ctrl-C again to exit</Text>
          <Text dimColor> | any other key to cancel</Text>
        </Box>
      ) : (
        <>
          {resolvedSegments.length > 0 && <StatusLine segments={resolvedSegments} />}
          {footerLines.length > 0 && (
            <Box flexDirection="column" paddingX={1} flexShrink={0}>
              {footerLines.map((line, index) =>
                line.segments && line.segments.length > 0 ? (
                  <Box key={`${index}:segments`} flexDirection="row">
                    {line.segments.map((segment, segmentIndex) => (
                      <React.Fragment key={`${index}:${segmentIndex}:${segment.content}`}>
                        {segmentIndex > 0 && <Text dimColor>{" | "}</Text>}
                        <Text dimColor={line.emphasis ? false : true} color={segment.color}>
                          {segment.content}
                        </Text>
                      </React.Fragment>
                    ))}
                  </Box>
                ) : (
                  <Text key={`${index}:${line.content ?? ""}`} dimColor={line.emphasis ? false : true} color={line.color}>
                    {line.content ?? ""}
                  </Text>
                ),
              )}
            </Box>
          )}
        </>
      )}
    </>
  );
}

function ReplBottomReplacement({
  askUserQuestion,
  permissionRequest,
  planReview,
  planReviewIndex,
}: {
  askUserQuestion?: AskUserQuestionState;
  permissionRequest?: PermissionRequestState;
  planReview?: import("@jarvis/tools").PlanReviewRequest | null;
  planReviewIndex: number;
}): React.ReactNode {
  if (askUserQuestion) {
    return (
      <AskUserQuestion
        questions={askUserQuestion.questions}
        onSubmit={askUserQuestion.onSubmit}
        onCancel={askUserQuestion.onCancel}
      />
    );
  }

  if (permissionRequest) {
    return (
      <PermissionRequest
        toolName={permissionRequest.toolName}
        description={permissionRequest.description}
        details={permissionRequest.details}
        patternLabel={permissionRequest.patternLabel}
        preview={permissionRequest.preview}
        onDecision={permissionRequest.onDecision}
      />
    );
  }

  if (planReview) {
    return <PlanReview plan={planReview} selectedIndex={planReviewIndex} />;
  }

  return null;
}

function ReplOverlaySurface({
  searchOpen,
  setSearchOpen,
  searchContents,
  setActiveSearchMatch,
  setSearchQuery,
  agents,
  agentsPanelVisible,
  agentsFocused,
  onCloseAgents,
}: {
  searchOpen: boolean;
  setSearchOpen: (value: boolean) => void;
  searchContents: string[];
  setActiveSearchMatch: (match: SearchMatch | null) => void;
  setSearchQuery: (query: string) => void;
  agents?: AgentStatusEntry[];
  agentsPanelVisible: boolean;
  agentsFocused: boolean;
  onCloseAgents: () => void;
}): React.ReactNode {
  if (searchOpen) {
    return (
      <SearchOverlay
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onSearch={(q) => computeMatches(searchContents, q)}
        onNavigate={setActiveSearchMatch}
        onActiveMatchChange={setActiveSearchMatch}
        onQueryChange={setSearchQuery}
      />
    );
  }

  if (agentsPanelVisible) {
    return (
      <AgentsPanel
        agents={agents ?? []}
        visible={agentsPanelVisible}
        focused={agentsFocused}
        onClose={onCloseAgents}
      />
    );
  }

  return null;
}

function ReplModalSurface({
  modelSelectorOpen,
  modelSelectorKnownModels,
  modelSelectorCurrentModel,
  modelSelectorCurrentEffort,
  effortSelectorLevels,
  onModelSelect,
  onModelSelectorCancel,
  onModelEffortChange,
  effortSelectorOpen,
  effortSelectorCurrent,
  onEffortSelect,
  onEffortSelectorCancel,
  onEffortSelectorChange,
  helpPopupOpen,
  helpPopupCommands,
  onHelpPopupClose,
  contextPanel,
  onContextPanelClose,
  mcpPanel,
  onMcpPanelClose,
}: {
  modelSelectorOpen: boolean;
  modelSelectorKnownModels: ModelInfo[];
  modelSelectorCurrentModel: string;
  modelSelectorCurrentEffort: string;
  effortSelectorLevels: readonly string[];
  onModelSelect?: (result: ModelSelectionResult) => void;
  onModelSelectorCancel?: () => void;
  onModelEffortChange?: (effort: string) => void;
  effortSelectorOpen: boolean;
  effortSelectorCurrent: string;
  onEffortSelect?: (effort: string) => void;
  onEffortSelectorCancel?: () => void;
  onEffortSelectorChange?: (effort: string) => void;
  helpPopupOpen: boolean;
  helpPopupCommands: HelpCommandEntry[];
  onHelpPopupClose?: () => void;
  contextPanel?: { title: string; subtitle?: string; lines: string[] } | null;
  onContextPanelClose?: () => void;
  mcpPanel?: { title: string; subtitle?: string; lines: string[] } | null;
  onMcpPanelClose?: () => void;
}): React.ReactNode {
  if (modelSelectorOpen && modelSelectorKnownModels.length > 0) {
    return (
      <Box flexDirection="column" paddingX={1} borderStyle="round" borderColor="cyan" flexShrink={0}>
        <ModelSelector
          currentModel={modelSelectorCurrentModel}
          currentEffort={modelSelectorCurrentEffort}
          effortLevels={effortSelectorLevels}
          knownModels={modelSelectorKnownModels}
          onSelect={(result: ModelSelectionResult) => onModelSelect?.(result)}
          onCancel={() => onModelSelectorCancel?.()}
          onEffortChange={(effort: string) => onModelEffortChange?.(effort)}
        />
      </Box>
    );
  }

  if (effortSelectorOpen) {
    return (
      <Box flexDirection="column" paddingX={1} borderStyle="round" borderColor="cyan" flexShrink={0}>
        <EffortSelector
          currentEffort={effortSelectorCurrent}
          levels={effortSelectorLevels}
          onSelect={(effort: string) => onEffortSelect?.(effort)}
          onCancel={() => onEffortSelectorCancel?.()}
          onChange={(effort: string) => onEffortSelectorChange?.(effort)}
        />
      </Box>
    );
  }

  if (helpPopupOpen && helpPopupCommands.length > 0) {
    return <HelpPopup commands={helpPopupCommands} onClose={() => onHelpPopupClose?.()} />;
  }

  if (contextPanel) {
    return (
      <ShellTextPanel
        title={contextPanel.title}
        subtitle={contextPanel.subtitle}
        lines={contextPanel.lines}
        accentColor="cyan"
        onClose={() => onContextPanelClose?.()}
      />
    );
  }

  if (mcpPanel) {
    return (
      <ShellTextPanel
        title={mcpPanel.title}
        subtitle={mcpPanel.subtitle}
        lines={mcpPanel.lines}
        accentColor="yellow"
        onClose={() => onMcpPanelClose?.()}
      />
    );
  }

  return null;
}














