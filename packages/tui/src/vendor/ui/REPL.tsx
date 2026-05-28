import { Box, Text, type Key, useApp, useInput } from "../ink-renderer/index.js";
import { AgentsPanel, type AgentStatusEntry } from "./AgentsPanel";
import type React from "react";
import { useCallback, useMemo, useRef, useState } from "react";
import { AskUserQuestion } from "./AskUserQuestion";
import type { AskQuestionDef } from "@jarvis/tools";
import type { ThreadEvent } from "@jarvis/agent";
import { CodexTimeline } from "../../presentation/CodexTimeline.js";
import {
  buildCodexTimelineState,
  buildSearchExcerpt,
  type CodexTaskSnapshot,
  type CodexTurnSnapshot,
} from "../../presentation/codex-timeline-state.js";
import { Divider } from "./Divider";
import { type Message, MessageList } from "./MessageList";
import { type PermissionAction, PermissionRequest } from "./PermissionRequest";
import { PromptInput } from "./PromptInput";
import { computeMatches, SearchOverlay } from "./SearchOverlay";
import { Spinner } from "./Spinner";
import { StatusLine, type StatusLineSegment } from "./StatusLine";
import type { SearchMatch } from "./SearchOverlay";
import type { TuiPresentationMode } from "../../presentation/contracts.js";

type REPLCommand = {
  name: string;
  description: string;
  onExecute: (args: string, fullInput: string) => void;
};

type PermissionRequestState = {
  toolName: string;
  description: string;
  details?: string;
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

  commands?: REPLCommand[];
  model?: string;
  statusSegments?: StatusLineSegment[];

  prefix?: string;
  placeholder?: string;
  history?: string[];

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
  commands = [],
  model,
  statusSegments,
  prefix = "\u276F",
  placeholder,
  history: externalHistory,
  renderMessage,
  spinner,
  spinnerTokenCount,
  spinnerVerb,
  spinnerStatus,
  spinnerDetails,
  spinnerRunning,
  spinnerCompleted,
  agents,
}: REPLProps): React.ReactNode {
  const { exit } = useApp();
  const [inputValue, setInputValue] = useState("");
  const [showAgents, setShowAgents] = useState(false);
  const [internalHistory, setInternalHistory] = useState<string[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearchMatch, setActiveSearchMatch] = useState<SearchMatch | null>(null);
  const [thinkingExpanded, setThinkingExpanded] = useState(false);
  const [toolResultsExpanded, setToolResultsExpanded] = useState(false);
  const submittingRef = useRef(false);

  const history = externalHistory ?? internalHistory;

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
          cmd.onExecute(cmdArgs, trimmed);
          return;
        }
      }

      submittingRef.current = true;
      setInputValue("");
      if (!externalHistory) {
        setInternalHistory((prev) => [trimmed, ...prev]);
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
      // Ctrl+C: first press interrupts, second within 1s exits (like Codex)
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
      if (key.ctrl && _input === "g") {
        setShowAgents((prev) => !prev);
      }
      if (key.ctrl && _input === "o") {
        setToolResultsExpanded((prev) => !prev);
      }
    },
    // Deactivate when search overlay is open so only SearchOverlay handles input.
    { isActive: !searchOpen },
  );

  const resolvedSegments = statusSegments ?? buildDefaultSegments(model);
  const showWelcome = welcome && messages.length === 0 && threadEvents.length === 0 && !isLoading;
  const showPermission = !!permissionRequest;
  const messageAreaFlexGrow = showWelcome ? 0 : 1;
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

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box flexDirection="column" flexGrow={messageAreaFlexGrow}>
        {showWelcome && <Box marginBottom={0}>{welcome}</Box>}

        <AgentsPanel
          agents={agents ?? []}
          visible={showAgents}
          onClose={() => setShowAgents(false)}
        />

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
      </Box>

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
          disabled={searchOpen}
          isLoading={isLoading}
          commands={promptCommands}
          history={history}
        />
      )}

      <Divider />

      {resolvedSegments.length > 0 && <StatusLine segments={resolvedSegments} />}
    </Box>
  );
}

function buildDefaultSegments(model?: string): StatusLineSegment[] {
  if (!model) return [];
  return [{ content: model, color: "green" }];
}
