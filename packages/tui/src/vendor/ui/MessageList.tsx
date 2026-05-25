import { Box, Text } from "../ink-renderer/index.js";
import type React from "react";
import { useState } from "react";
import { Spinner } from "./Spinner";
import { getStableKeys, getStableLineEntries } from "./utils/stableKeys";

export type TaskResultItem = {
  id: string;
  subject: string;
  status: "pending" | "in_progress" | "completed";
};

export type PlanStep = {
  step: string;
  files?: string[];
  verification?: string;
};

export type MessageContent =
  | { type: "text"; text: string }
  | {
      type: "tool_use";
      toolName: string;
      input: string;
      result?: string;
      status?: "running" | "success" | "error";
    }
  | { type: "thinking"; text: string; collapsed?: boolean }
  | { type: "diff"; filename: string; diff: string }
  | { type: "code"; language?: string; code: string }
  | { type: "error"; message: string; details?: string }
  | {
      type: "task_result";
      tasks: TaskResultItem[];
      counts: { pending: number; in_progress: number; completed: number };
    }
  | { type: "plan"; summary: string; steps?: PlanStep[] };

/**
 * Display-oriented message type for rendering in the terminal UI.
 *
 * This type adds `id` and `timestamp` fields for UI purposes and supports
 * rich `MessageContent[]` for rendering tool calls, diffs, code blocks, etc.
 * It is distinct from the protocol-level `Message` type in
 * `@claude-code-kit/agent`, which represents raw LLM conversation messages.
 * The `useAgent` hook handles conversion between the two formats automatically.
 */
export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string | MessageContent[];
  timestamp?: number;
};

export type MessageListProps = {
  messages: Message[];
  streamingContent?: string | null;
  renderMessage?: (message: Message) => React.ReactNode;
  allThinkingExpanded?: boolean;
  allToolResultsExpanded?: boolean;
};

const ROLE_CONFIG = {
  user: { icon: "\u276F", label: "You", color: "cyan" as const },
  assistant: { icon: "\u25CF", label: "Jarvis", color: "#DA7756" as const },
  system: { icon: "\u273B", label: "System", color: undefined },
} as const;

const GUTTER = "\u23BF"; // ⎿

function TextBlock({ text, dim }: { text: string; dim?: boolean }): React.ReactNode {
  const lines = getStableLineEntries(text, "text");
  return (
    <>
      {lines.map(({ key, line }) => (
        <Box key={key} marginLeft={2}>
          <Text dimColor={dim}>{line}</Text>
        </Box>
      ))}
    </>
  );
}

function ToolUseBlock({
  content,
  allExpanded,
}: {
  content: Extract<MessageContent, { type: "tool_use" }>;
  allExpanded?: boolean;
}): React.ReactNode {
  const [localExpanded, setLocalExpanded] = useState(false);
  const expanded = allExpanded ?? localExpanded;

  const inputLines = getStableLineEntries(content.input, `${content.toolName}:input`);
  const resultLines =
    content.result != null
      ? getStableLineEntries(content.result, `${content.toolName}:result`)
      : [];
  const statusColor =
    content.status === "error" ? "red" : content.status === "success" ? "green" : undefined;

  const isRunning = content.status === "running";
  const hasResult = content.result != null;

  // Collapsed: show summary line only (like openclaw's chat-tool-msg-summary)
  if (!expanded && !isRunning) {
    const preview =
      hasResult
        ? content.result!.slice(0, 80).replace(/\n/g, " ")
        : inputLines.length > 0
          ? content.input.slice(0, 80).replace(/\n/g, " ")
          : "";
    return (
      <Box marginLeft={2}>
        <Box onClick={() => setLocalExpanded(true)}>
          <Text dimColor>{GUTTER} </Text>
          <Text bold>{content.toolName}</Text>
          {preview ? (
            <Text dimColor>
              {" "}
              {preview}
              {preview.length >= 80 ? "…" : ""}
            </Text>
          ) : null}
          {hasResult && (
            <Text color={statusColor}> {content.status === "error" ? "(error)" : "(done)"}</Text>
          )}
          <Text dimColor> (Ctrl+O to expand)</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box onClick={() => setLocalExpanded((c) => !c)}>
        <Text dimColor>{GUTTER} </Text>
        <Text bold>{content.toolName}</Text>
        <Text dimColor> {expanded ? "(click to collapse)" : ""}</Text>
      </Box>
      {inputLines.map(({ key, line }) => (
        <Box key={key} marginLeft={4}>
          <Text dimColor>{line}</Text>
        </Box>
      ))}
      {isRunning && (
        <Box marginLeft={4}>
          <Spinner label={content.toolName} showElapsed />
        </Box>
      )}
      {hasResult && (
        <Box flexDirection="column" marginLeft={4}>
          <Box>
            <Text dimColor>{GUTTER} </Text>
            <Text color={statusColor}>result ({content.status ?? "done"})</Text>
          </Box>
          {resultLines.map(({ key, line }) => (
            <Box key={key} marginLeft={6}>
              <Text color={statusColor} dimColor={!statusColor}>
                {line}
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}

function ThinkingBlock({
  content,
  allExpanded,
}: {
  content: Extract<MessageContent, { type: "thinking" }>;
  allExpanded?: boolean;
}): React.ReactNode {
  const [localCollapsed, setLocalCollapsed] = useState(content.collapsed ?? true);
  const collapsed = allExpanded !== undefined ? !allExpanded : localCollapsed;
  const lines = getStableLineEntries(content.text, "thinking");

  return (
    <Box flexDirection="column" marginLeft={2}>
      {/* eslint-disable-next-line react/no-unknown-property */}
      <Box onClick={() => setLocalCollapsed((c) => !c)}>
        <Text color="#DA7756">{"\u273B"} </Text>
        <Text dimColor>
          {collapsed ? `Reasoning (Ctrl+T to expand)` : `Reasoning (Ctrl+T to collapse)`}
        </Text>
      </Box>
      {!collapsed &&
        lines.map(({ key, line }) => (
          <Box key={key} marginLeft={4}>
            <Text dimColor>{line}</Text>
          </Box>
        ))}
    </Box>
  );
}

function DiffBlock({
  content,
}: {
  content: Extract<MessageContent, { type: "diff" }>;
}): React.ReactNode {
  const diffLines = getStableLineEntries(content.diff, `${content.filename}:diff`);

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text dimColor>{GUTTER} </Text>
        <Text bold>{content.filename}</Text>
      </Box>
      {diffLines.map(({ key, line }) => {
        let color: string | undefined;
        if (line.startsWith("+")) color = "green";
        else if (line.startsWith("-")) color = "red";
        else if (line.startsWith("@")) color = "cyan";
        return (
          <Box key={key} marginLeft={4}>
            <Text color={color} dimColor={!color}>
              {line}
            </Text>
          </Box>
        );
      })}
    </Box>
  );
}

function CodeBlock({
  content,
}: {
  content: Extract<MessageContent, { type: "code" }>;
}): React.ReactNode {
  const codeLines = getStableLineEntries(content.code, `code:${content.language ?? "plain"}`);

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Text dimColor>```{content.language ?? ""}</Text>
      {codeLines.map(({ key, line }) => (
        <Box key={key} marginLeft={2}>
          <Text>{line}</Text>
        </Box>
      ))}
      <Text dimColor>```</Text>
    </Box>
  );
}

function ErrorBlock({
  content,
}: {
  content: Extract<MessageContent, { type: "error" }>;
}): React.ReactNode {
  const detailLines = content.details ? getStableLineEntries(content.details, "error-details") : [];

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text color="red">{"\u2716"} Error: </Text>
        <Text color="red">{content.message}</Text>
      </Box>
      {detailLines.map(({ key, line }) => (
        <Box key={key} marginLeft={4}>
          <Text color="red" dimColor>
            {line}
          </Text>
        </Box>
      ))}
    </Box>
  );
}

const STATUS_ICONS: Record<string, string> = {
  pending: "⏳", // ⏳
  in_progress: "\u{1F504}", // 🔄
  completed: "✅", // ✅
};

function TaskBlock({
  content,
}: {
  content: Extract<MessageContent, { type: "task_result" }>;
}): React.ReactNode {
  const { tasks, counts } = content;
  const summaryParts: string[] = [];
  if (counts.pending > 0) summaryParts.push(`${counts.pending} pending`);
  if (counts.in_progress > 0) summaryParts.push(`${counts.in_progress} in progress`);
  if (counts.completed > 0) summaryParts.push(`${counts.completed} completed`);

  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text dimColor>{GUTTER} </Text>
        <Text bold>Tasks</Text>
        {summaryParts.length > 0 && (
          <Text dimColor> ({summaryParts.join(", ")})</Text>
        )}
      </Box>
      {tasks.map((task) => (
        <Box key={task.id} marginLeft={4}>
          <Text>{STATUS_ICONS[task.status] ?? "  "} </Text>
          <Text dimColor={task.status === "completed"}>{task.subject}</Text>
        </Box>
      ))}
    </Box>
  );
}

function PlanBlock({
  content,
}: {
  content: Extract<MessageContent, { type: "plan" }>;
}): React.ReactNode {
  const steps = content.steps ?? [];
  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box>
        <Text dimColor>{GUTTER} </Text>
        <Text bold color="#DA7756">Plan: </Text>
        <Text color="#DA7756">{content.summary}</Text>
      </Box>
      {steps.map((step, i) => (
        <Box key={`plan-step-${i}`} marginLeft={4} flexDirection="column">
          <Box>
            <Text dimColor>{String(i + 1)}. </Text>
            <Text>{step.step}</Text>
          </Box>
          {step.files && step.files.length > 0 && (
            <Box marginLeft={4}>
              <Text dimColor>files: {step.files.join(", ")}</Text>
            </Box>
          )}
          {step.verification && (
            <Box marginLeft={4}>
              <Text dimColor>verify: {step.verification}</Text>
            </Box>
          )}
        </Box>
      ))}
    </Box>
  );
}

function ContentBlock({
  block,
  allThinkingExpanded,
  allToolResultsExpanded,
}: {
  block: MessageContent;
  allThinkingExpanded?: boolean;
  allToolResultsExpanded?: boolean;
}): React.ReactNode {
  switch (block.type) {
    case "text":
      return <TextBlock text={block.text} />;
    case "tool_use":
      return <ToolUseBlock content={block} allExpanded={allToolResultsExpanded} />;
    case "thinking":
      return <ThinkingBlock content={block} allExpanded={allThinkingExpanded} />;
    case "diff":
      return <DiffBlock content={block} />;
    case "code":
      return <CodeBlock content={block} />;
    case "error":
      return <ErrorBlock content={block} />;
    case "task_result":
      return <TaskBlock content={block} />;
    case "plan":
      return <PlanBlock content={block} />;
    default:
      return null;
  }
}

function getMessageContentFingerprint(block: MessageContent): string {
  return `${block.type}:${JSON.stringify(block)}`;
}

function MessageItem({
  message,
  renderMessage,
  allThinkingExpanded,
  allToolResultsExpanded,
}: {
  message: Message;
  renderMessage?: (message: Message) => React.ReactNode;
  allThinkingExpanded?: boolean;
  allToolResultsExpanded?: boolean;
}): React.ReactNode {
  if (renderMessage) {
    return renderMessage(message);
  }

  const config = ROLE_CONFIG[message.role];
  const isSystem = message.role === "system";

  if (typeof message.content === "string") {
    const textLines = getStableLineEntries(message.content, `${message.id}:message`);
    return (
      <Box flexDirection="column">
        <Box>
          <Text color={config.color} dimColor={isSystem}>
            {config.icon}
          </Text>
          <Text color={config.color} dimColor={isSystem} bold={!isSystem}>
            {" "}
            {config.label}
          </Text>
        </Box>
        {textLines.map(({ key, line }) => (
          <Box key={key} marginLeft={2}>
            <Text dimColor={isSystem}>{line}</Text>
          </Box>
        ))}
      </Box>
    );
  }

  const blockKeys = getStableKeys(message.content, getMessageContentFingerprint);

  return (
    <Box flexDirection="column">
      <Box>
        <Text color={config.color} dimColor={isSystem}>
          {config.icon}
        </Text>
        <Text color={config.color} dimColor={isSystem} bold={!isSystem}>
          {" "}
          {config.label}
        </Text>
      </Box>
      {message.content.map((block, i) => (
        <ContentBlock
          key={blockKeys[i]}
          block={block}
          allThinkingExpanded={allThinkingExpanded}
          allToolResultsExpanded={allToolResultsExpanded}
        />
      ))}
    </Box>
  );
}

export function MessageList({
  messages,
  streamingContent,
  renderMessage,
  allThinkingExpanded,
  allToolResultsExpanded,
}: MessageListProps): React.ReactNode {
  const streamingLines =
    streamingContent != null && streamingContent.length > 0
      ? getStableLineEntries(streamingContent, "streaming")
      : [];

  return (
    <Box flexDirection="column">
      {messages.map((message, i) => (
        <Box key={message.id} flexDirection="column" marginTop={i > 0 ? 1 : 0}>
          <MessageItem
            message={message}
            renderMessage={renderMessage}
            allThinkingExpanded={allThinkingExpanded}
            allToolResultsExpanded={allToolResultsExpanded}
          />
        </Box>
      ))}

      {streamingContent != null && streamingContent.length > 0 && (
        <Box flexDirection="column" marginTop={messages.length > 0 ? 1 : 0}>
          <Box>
            <Text color="#DA7756">{"\u25CF"}</Text>
            <Text color="#DA7756" bold>
              {" "}
              Jarvis
            </Text>
          </Box>
          {streamingLines.map(({ key, line }, i) => (
            <Box key={key} marginLeft={2}>
              <Text>
                {line}
                {i === streamingLines.length - 1 && <Text color="#DA7756">{"\u2588"}</Text>}
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
