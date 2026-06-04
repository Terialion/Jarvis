import {
  Box,
  Text,
  type Key,
  useApp,
  useHasSelection,
  useInput,
  useSelection,
  ScrollBox,
  type ScrollBoxHandle,
} from "../ink-renderer/index.js";
import { AgentsPanel, type AgentStatusEntry } from "./AgentsPanel";
import React from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AskUserQuestion } from "./AskUserQuestion";
import { PlanReview } from "./PlanReview";
import type { AskQuestionDef } from "@jarvis/tools";
import type { ThreadEvent, ModelInfo } from "@jarvis/agent";
import { CodexTimeline } from "../../presentation/CodexTimeline.js";
import { HelpPopup, type HelpCommandEntry } from "./HelpPopup";
import { ShellTextPanel } from "./ShellTextPanel";
import {
  buildCodexTimelineState,
  buildSearchExcerpt,
  type CodexTaskSnapshot,
  type CodexTurnSnapshot,
} from "../../presentation/codex-timeline-state.js";
import { Divider } from "./Divider";
import { type Message, MessageList } from "./MessageList";
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
  const [followOutput, setFollowOutput] = useState(true);
  const [scrollPositionKind, setScrollPositionKind] = useState<"following" | "history" | "selection">("following");
  const submittingRef = useRef(false);
  const hasSelection = useHasSelection();
  const { clearSelection, copySelectionNoClear } = useSelection();

  const history = externalHistory ?? internalHistory;
  const overlaysOpen =
    searchOpen || modelSelectorOpen || effortSelectorOpen || helpPopupOpen || !!contextPanel || !!mcpPanel;
  const viewportHotkeysActive = !overlaysOpen && !agentsFocused;

  useRegisterKeybindingContext("Chat", !overlaysOpen && !planReview);
  useRegisterKeybindingContext("Scroll", viewportHotkeysActive);

  const stopFollowingOutput = useCallback(
    (kind: "history" | "selection" = "history") => {
      setFollowOutput(false);
      setScrollPositionKind(kind);
    },
    [],
  );

  const getRemainingScrollDistance = useCallback(() => {
    const handle = scrollRef.current;
    if (!handle) return Number.POSITIVE_INFINITY;
    return Math.max(0, handle.getScrollHeight() - handle.getViewportHeight() - handle.getScrollTop());
  }, []);

  const resumeFollowingOutput = useCallback(() => {
    scrollRef.current?.scrollToBottom();
    setFollowOutput(true);
    setScrollPositionKind("following");
  }, []);

  const handleViewportScrollBy = useCallback(
    (dy: number) => {
      scrollRef.current?.scrollBy(dy);
      const nextKind = hasSelection ? "selection" : "history";
      stopFollowingOutput(nextKind);
      if (dy > 0) {
        setTimeout(() => {
          if (hasSelection) return;
          const remaining = getRemainingScrollDistance();
          if (remaining <= 2) {
            resumeFollowingOutput();
          } else {
            setScrollPositionKind(nextKind);
          }
        }, 0);
      }
    },
    [getRemainingScrollDistance, hasSelection, resumeFollowingOutput, stopFollowingOutput],
  );

  const handleViewportScrollToTop = useCallback(() => {
    scrollRef.current?.scrollTo(0);
    stopFollowingOutput(hasSelection ? "selection" : "history");
  }, [hasSelection, stopFollowingOutput]);

  useEffect(() => {
    if (hasSelection) {
      stopFollowingOutput("selection");
      return;
    }
    if (!followOutput && getRemainingScrollDistance() <= 2) {
      resumeFollowingOutput();
      return;
    }
    if (followOutput) {
      setScrollPositionKind("following");
      return;
    }
    setScrollPositionKind("history");
  }, [followOutput, getRemainingScrollDistance, hasSelection, resumeFollowingOutput, stopFollowingOutput]);

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
        resumeFollowingOutput();
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
          resumeFollowingOutput();
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
      // Agents panel focus mode 鈥?route keys to panel
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
          if (onExit) { onExit(); } else { exit(); }
          return;
        }
        lastCtrlCPressRef.current = now;
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
      // Any other key resets the double-press timer
      lastCtrlCPressRef.current = 0;

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
      // Ctrl+G handled earlier for focus/panel toggle 鈥?skip here
      if (key.ctrl && _input === "o") {
        setToolResultsExpanded((prev) => !prev);
      }
      // Shift+Tab: cycle permission modes (suggest 鈫?auto-edit 鈫?full-auto 鈫?suggest)
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
  const planSidebarWidth = 52;
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

  const finalViewportStatusLine = useMemo((): StatusDetailLine => {
    if (scrollPositionKind === "selection") {
      return {
        content: "[Selection mode] Follow paused | Ctrl+C copies | Esc clears | End resumes live output",
        color: "cyan",
        emphasis: true,
      };
    }
    if (scrollPositionKind === "history") {
      return {
        content: "[History mode] Follow paused | Scroll freely | End resumes live output",
        color: "yellow",
        emphasis: true,
      };
    }
    return {
      content: isLoading
        ? "[Live mode] Following output | pinned to the newest live step"
        : "[Live mode] Following output | pinned to the latest message",
      color: "green",
      emphasis: true,
    };
  }, [isLoading, scrollPositionKind]);

  const combinedStatusDetailLines = useMemo(
    () => [finalViewportStatusLine, ...statusDetailLines],
    [finalViewportStatusLine, statusDetailLines],
  );

  const transcriptBody = useMemo(
    () => (
      <>
        {showWelcome && <Box marginBottom={0}>{welcome}</Box>}

        {presentationMode === "codex" ? (
          <CodexTimeline state={codexState} search={codexSearchState} detailsExpanded={toolResultsExpanded} />
        ) : (
          <MessageList
            messages={messages}
            streamingContent={streamingContent}
            streamingThinking={streamingThinking}
            streamingElapsedMs={streamingElapsedMs}
            renderMessage={renderMessage}
            allThinkingExpanded={thinkingExpanded}
            allToolResultsExpanded={toolResultsExpanded}
            searchQuery={searchQuery}
            activeSearchMatch={activeSearchMatch}
          />
        )}

        {presentationMode !== "codex" && isLoading && !streamingContent && !streamingThinking && (
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
        )}
      </>
    ),
    [
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
    ],
  );

  const shellScrollableBody = (
    <Box flexDirection="column" width="100%">
      <Box flexDirection="row" flexGrow={contentAreaFlexGrow}>
        <Box flexDirection="column" flexGrow={messageAreaFlexGrow}>
          {transcriptBody}
        </Box>

        {planReview && (
          <Box width={planSidebarWidth} flexShrink={0} marginLeft={1}>
            <PlanReview
              plan={planReview}
              selectedIndex={planReviewIndex}
            />
          </Box>
        )}
      </Box>

      <AgentsPanel
        agents={agents ?? []}
        visible={agentsPanelVisible}
        focused={agentsFocused}
        onClose={() => { setShowAgents(false); setAgentsFocused(false); }}
      />

      {searchOpen && (
        <SearchOverlay
          isOpen={searchOpen}
          onClose={() => setSearchOpen(false)}
          onSearch={(q) => computeMatches(searchContents, q)}
          onNavigate={setActiveSearchMatch}
          onActiveMatchChange={setActiveSearchMatch}
          onQueryChange={setSearchQuery}
        />
      )}

      {modelSelectorOpen && modelSelectorKnownModels.length > 0 && (
        <Box flexDirection="column" paddingX={1} borderStyle="round" borderColor="cyan">
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
      )}

      {effortSelectorOpen && (
        <Box flexDirection="column" paddingX={1} borderStyle="round" borderColor="cyan">
          <EffortSelector
            currentEffort={effortSelectorCurrent}
            levels={effortSelectorLevels}
            onSelect={(effort: string) => onEffortSelect?.(effort)}
            onCancel={() => onEffortSelectorCancel?.()}
            onChange={(effort: string) => onEffortSelectorChange?.(effort)}
          />
        </Box>
      )}

      {helpPopupOpen && helpPopupCommands.length > 0 && (
        <HelpPopup
          commands={helpPopupCommands}
          onClose={() => onHelpPopupClose?.()}
        />
      )}

      {contextPanel && (
        <ShellTextPanel
          title={contextPanel.title}
          subtitle={contextPanel.subtitle}
          lines={contextPanel.lines}
          accentColor="cyan"
          onClose={() => onContextPanelClose?.()}
        />
      )}

      {mcpPanel && (
        <ShellTextPanel
          title={mcpPanel.title}
          subtitle={mcpPanel.subtitle}
          lines={mcpPanel.lines}
          accentColor="yellow"
          onClose={() => onMcpPanelClose?.()}
        />
      )}

      <Divider />

      {askUserQuestion ? (
        <AskUserQuestion
          questions={askUserQuestion.questions}
          onSubmit={askUserQuestion.onSubmit}
          onCancel={askUserQuestion.onCancel}
        />
      ) : showPermission ? (
        <PermissionRequest
          toolName={permissionRequest.toolName}
          description={permissionRequest.description}
          details={permissionRequest.details}
          patternLabel={permissionRequest.patternLabel}
          preview={permissionRequest.preview}
          onDecision={permissionRequest.onDecision}
        />
      ) : (
        <PromptInput
          value={inputValue}
          onChange={setInputValue}
          onSubmit={handleSubmit}
          prefix={prefix}
          placeholder={placeholder}
          disabled={overlaysOpen || !!planReview}
          isLoading={isLoading}
          commands={promptCommands}
          history={history}
          fileEntries={fileEntries}
          onFileSearch={onFileSearch}
        />
      )}

      <Divider />

      {resolvedSegments.length > 0 && <StatusLine segments={resolvedSegments} />}
      {combinedStatusDetailLines.length > 0 && (
        <Box flexDirection="column" paddingX={1}>
          {combinedStatusDetailLines.map((line, index) => (
            line.segments && line.segments.length > 0 ? (
              <Box key={`${index}:segments`} flexDirection="row">
                {line.segments.map((segment, segmentIndex) => (
                  <React.Fragment key={`${index}:${segmentIndex}:${segment.content}`}>
                    {segmentIndex > 0 && <Text dimColor>{' | '}</Text>}
                    <Text dimColor={line.emphasis ? false : true} color={segment.color}>
                      {segment.content}
                    </Text>
                  </React.Fragment>
                ))}
              </Box>
            ) : (
              <Text key={`${index}:${line.content ?? ''}`} dimColor={line.emphasis ? false : true} color={line.color}>
                {line.content ?? ""}
              </Text>
            )
          ))}
        </Box>
      )}
    </Box>
  );

  return (
    <Box flexDirection="column" flexGrow={1}>
      <ScrollBox
        ref={scrollRef}
        flexDirection="column"
        flexGrow={1}
        stickyScroll={followOutput && !hasSelection}
      >
        {shellScrollableBody}
      </ScrollBox>
    </Box>
  );
}

function buildDefaultSegments(model?: string): StatusLineSegment[] {
  if (!model) return [];
  return [{ content: model, color: "green" }];
}

