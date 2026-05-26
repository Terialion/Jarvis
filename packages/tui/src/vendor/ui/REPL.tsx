import { Box, type Key, useApp, useInput } from "../ink-renderer/index.js";
import type React from "react";
import { useCallback, useRef, useState } from "react";
import { AskUserQuestion } from "./AskUserQuestion";
import type { AskQuestionDef } from "@jarvis/tools";
import { Divider } from "./Divider";
import { type Message, MessageList } from "./MessageList";
import { type PermissionAction, PermissionRequest } from "./PermissionRequest";
import { PromptInput } from "./PromptInput";
import { computeMatches, SearchOverlay } from "./SearchOverlay";
import { Spinner } from "./Spinner";
import { StatusLine, type StatusLineSegment } from "./StatusLine";

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
  spinnerRunning?: string;
  spinnerCompleted?: string[];
};

export function REPL({
  onSubmit,
  onExit,
  onInterrupt,
  messages,
  isLoading = false,
  streamingContent,
  streamingThinking,
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
  spinnerRunning,
  spinnerCompleted,
}: REPLProps): React.ReactNode {
  const { exit } = useApp();
  const [inputValue, setInputValue] = useState("");
  const [internalHistory, setInternalHistory] = useState<string[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
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
        setThinkingExpanded((prev) => !prev);
      }
      if (key.ctrl && _input === "o") {
        setToolResultsExpanded((prev) => !prev);
      }
    },
    // Deactivate when search overlay is open so only SearchOverlay handles input.
    { isActive: !searchOpen },
  );

  const resolvedSegments = statusSegments ?? buildDefaultSegments(model);
  const showWelcome = welcome && messages.length === 0 && !isLoading;
  const showPermission = !!permissionRequest;

  return (
    <Box flexDirection="column" flexGrow={1}>
      <Box flexDirection="column" flexGrow={1}>
        {showWelcome && <Box marginBottom={1}>{welcome}</Box>}

        <MessageList
          messages={messages}
          streamingContent={streamingContent}
          streamingThinking={streamingThinking}
          renderMessage={renderMessage}
          allThinkingExpanded={thinkingExpanded}
          allToolResultsExpanded={toolResultsExpanded}
        />

        {isLoading && !streamingContent && !streamingThinking && (
          <Box marginTop={messages.length > 0 ? 1 : 0}>
            {spinner ?? (
              <Spinner
                tokenCount={spinnerTokenCount}
                verb={spinnerVerb}
                status={spinnerStatus}
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
          onSearch={(q) => computeMatches(messageContents, q)}
          onNavigate={() => {}}
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
