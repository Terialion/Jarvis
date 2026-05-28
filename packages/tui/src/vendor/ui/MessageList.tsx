import { Ansi, Box, Text } from "../ink-renderer/index.js";
import type React from "react";
import { useEffect, useState } from "react";
import { Markdown } from "./Markdown";
import type { SearchMatch } from "./SearchOverlay";
import { Spinner } from "./Spinner";
import { StreamCursor } from "./StreamCursor";
import { formatDuration, formatToolLine } from "./tool-display";
import { getStableKeys, getStableLineEntries } from "./utils/stableKeys";

let highlightFn: ((code: string, opts: { language?: string }) => string) | null | undefined;

async function getHighlighter(): Promise<((code: string, opts: { language?: string }) => string) | null> {
  if (highlightFn !== undefined) return highlightFn;
  try {
    const mod = await import("cli-highlight");
    highlightFn = (mod as { highlight: (code: string, opts: { language?: string }) => string }).highlight;
  } catch {
    highlightFn = null;
  }
  return highlightFn;
}

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
      durationMs?: number;
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

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string | MessageContent[];
  timestamp?: number;
};

export type MessageListProps = {
  messages: Message[];
  streamingContent?: string | null;
  streamingThinking?: string | null;
  streamingElapsedMs?: number;
  renderMessage?: (message: Message) => React.ReactNode;
  allThinkingExpanded?: boolean;
  allToolResultsExpanded?: boolean;
  searchQuery?: string;
  activeSearchMatch?: SearchMatch | null;
};

const ROLE_CONFIG = {
  user: { icon: ">", label: "You", color: "cyan" as const, railColor: "#1D6F8C" },
  assistant: { icon: "o", label: "Jarvis", color: "#DA7756" as const, railColor: "#7C4A39" },
  system: { icon: "-", label: "System", color: undefined, railColor: "#5C6470" },
} as const;

const RAIL_MARK = "|";
const GUTTER = ">";
const CARD_BG = "#1F2530";
const CARD_BG_SOFT = "#232A35";
const CARD_BG_SUCCESS = "#1D2D25";
const CARD_BG_ERROR = "#342224";
const SEARCH_BG = "#1A2533";

function parseToolArgs(input: string): Record<string, unknown> | undefined {
  const trimmed = input.trim();
  if (!trimmed.startsWith("{") && !trimmed.startsWith("[")) return undefined;
  try {
    const parsed = JSON.parse(trimmed) as Record<string, unknown>;
    return parsed && typeof parsed === "object" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function formatElapsed(elapsedMs?: number): string | null {
  if (!elapsedMs || elapsedMs <= 0) return null;
  const seconds = Math.floor(elapsedMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds.toString().padStart(2, "0")}s`;
  }
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours}h ${minutes}m`;
}

function cleanProgressLine(line: string): string {
  return line
    .replace(/```/g, "")
    .replace(/^[-*+\d.)\s>]+/, "")
    .replace(/[*_`#]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function extractProgressLines(text: string, limit = 4): string[] {
  const fragments = text
    .replace(/\r/g, "")
    .split("\n")
    .flatMap((line) =>
      line
        .split(/(?<=[.!?。！？])\s+/)
        .map((part) => cleanProgressLine(part))
        .filter(Boolean),
    );

  const deduped: string[] = [];
  for (const fragment of fragments) {
    if (fragment.length < 8) continue;
    if (deduped[deduped.length - 1] !== fragment) {
      deduped.push(fragment);
    }
  }

  return deduped.slice(-limit);
}

export function summarizeToolUse(toolName: string, input: string): string {
  return formatToolLine(toolName, parseToolArgs(input)) || input || toolName;
}

function getMessagePlainText(message: Message): string {
  if (typeof message.content === "string") {
    return message.content;
  }
  return message.content
    .map((block) => {
      if ("text" in block) return block.text;
      if (block.type === "code") return block.code;
      if (block.type === "error") return `${block.message} ${block.details ?? ""}`.trim();
      if (block.type === "task_result") return block.tasks.map((task) => task.subject).join(" ");
      if (block.type === "plan") return `${block.summary} ${(block.steps ?? []).map((step) => step.step).join(" ")}`.trim();
      if ("input" in block) return `${block.input} ${block.result ?? ""}`.trim();
      return "";
    })
    .join(" ");
}

export function buildSearchExcerpt(message: Message, query: string): string | null {
  if (!query) return null;
  const text = getMessagePlainText(message).replace(/\s+/g, " ").trim();
  if (!text) return null;
  const lowerText = text.toLowerCase();
  const lowerQuery = query.toLowerCase();
  const matchIndex = lowerText.indexOf(lowerQuery);
  if (matchIndex === -1) return null;
  const start = Math.max(0, matchIndex - 24);
  const end = Math.min(text.length, matchIndex + query.length + 24);
  const prefix = start > 0 ? "..." : "";
  const suffix = end < text.length ? "..." : "";
  return `${prefix}${text.slice(start, end)}${suffix}`;
}

function MessageRail({
  color,
  label,
  body,
  isActiveSearchHit = false,
  searchExcerpt,
}: {
  color?: string;
  label: React.ReactNode;
  body: React.ReactNode;
  isActiveSearchHit?: boolean;
  searchExcerpt?: string | null;
}): React.ReactNode {
  return (
    <Box flexDirection="row" marginTop={1} backgroundColor={isActiveSearchHit ? SEARCH_BG : undefined}>
      <Box marginRight={1}>
        <Text color={color}>{RAIL_MARK}</Text>
      </Box>
      <Box flexDirection="column" flexGrow={1}>
        <Box marginBottom={1}>{label}</Box>
        {searchExcerpt && (
          <Box marginBottom={1}>
            <Text dimColor color="cyan">Search hit | {searchExcerpt}</Text>
          </Box>
        )}
        {body}
      </Box>
    </Box>
  );
}

function BlockShell({
  title,
  titleColor,
  backgroundColor = CARD_BG,
  children,
}: {
  title: React.ReactNode;
  titleColor?: string;
  backgroundColor?: string;
  children?: React.ReactNode;
}): React.ReactNode {
  return (
    <Box flexDirection="column" marginLeft={2}>
      <Box flexDirection="column" backgroundColor={backgroundColor} paddingLeft={1} paddingRight={1}>
        <Box marginBottom={children ? 1 : 0}>
          <Text dimColor>{GUTTER} </Text>
          <Text color={titleColor} bold>{title}</Text>
        </Box>
        {children}
      </Box>
    </Box>
  );
}

function TextBlock({ text, dim }: { text: string; dim?: boolean }): React.ReactNode {
  return (
    <Box marginLeft={2}>
      {dim ? (
        <Text dimColor>{text}</Text>
      ) : (
        <Markdown>{text}</Markdown>
      )}
    </Box>
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
  const label = summarizeToolUse(content.toolName, content.input);
  const inputLines = getStableLineEntries(content.input, `${content.toolName}:input`);
  const resultLines = content.result ? getStableLineEntries(content.result, `${content.toolName}:result`) : [];
  const backgroundColor =
    content.status === "success" ? CARD_BG_SUCCESS : content.status === "error" ? CARD_BG_ERROR : CARD_BG_SOFT;

  if (!expanded && content.status !== "running") {
    return (
      <BlockShell
        title={label}
        titleColor={content.status === "error" ? "#F07C82" : "#E4E7EC"}
        backgroundColor={backgroundColor}
      >
        <Box onClick={() => setLocalExpanded(true)}>
          {content.durationMs != null && <Text dimColor>{formatDuration(content.durationMs)}</Text>}
          <Text dimColor>{content.durationMs != null ? " | " : ""}</Text>
          <Text dimColor>{content.status === "error" ? "Ctrl+O to inspect failure" : "Ctrl+O to inspect"}</Text>
        </Box>
      </BlockShell>
    );
  }

  return (
    <BlockShell title={label} titleColor="#E4E7EC" backgroundColor={backgroundColor}>
      <Box onClick={() => setLocalExpanded((value) => !value)} marginBottom={1}>
        <Text dimColor>{expanded ? "expanded" : "collapsed"}</Text>
        <Text dimColor> | Ctrl+O toggles details</Text>
      </Box>
      {inputLines.map(({ key, line }) => (
        <Box key={key} marginLeft={2}>
          <Text dimColor>{line}</Text>
        </Box>
      ))}
      {content.status === "running" && (
        <Box marginLeft={2}>
          <Spinner verb={label} showElapsed />
        </Box>
      )}
      {content.result && (
        <Box flexDirection="column" marginTop={1} marginLeft={2}>
          <Text color={content.status === "error" ? "#F07C82" : "#89D99D"}>Result</Text>
          {resultLines.map(({ key, line }) => (
            <Box key={key} marginLeft={2}>
              <Text dimColor={content.status !== "error"} color={content.status === "error" ? "#F07C82" : undefined}>
                {line}
              </Text>
            </Box>
          ))}
        </Box>
      )}
    </BlockShell>
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
  const previewLines = extractProgressLines(content.text, 2);
  const preview = previewLines.join(" ").slice(0, 96);
  const lines = getStableLineEntries(content.text, "thinking");

  return (
    <BlockShell title={collapsed ? "Reasoning" : "Reasoning details"} backgroundColor={CARD_BG_SOFT}>
      <Box onClick={() => setLocalCollapsed((value) => !value)} marginBottom={!collapsed ? 1 : 0}>
        <Text dimColor>{collapsed ? (preview || "Model is reasoning") : "Ctrl+T to collapse"}</Text>
      </Box>
      {!collapsed &&
        lines.map(({ key, line }) => (
          <Box key={key} marginLeft={2}>
            <Text dimColor>{line}</Text>
          </Box>
        ))}
    </BlockShell>
  );
}

function DiffBlock({ content }: { content: Extract<MessageContent, { type: "diff" }> }): React.ReactNode {
  const diffLines = getStableLineEntries(content.diff, `${content.filename}:diff`);

  return (
    <BlockShell title={content.filename} backgroundColor={CARD_BG_SOFT}>
      {diffLines.map(({ key, line }) => {
        let color: string | undefined;
        if (line.startsWith("+")) color = "green";
        else if (line.startsWith("-")) color = "red";
        else if (line.startsWith("@")) color = "cyan";
        return (
          <Box key={key} marginLeft={2}>
            <Text color={color} dimColor={!color}>
              {line}
            </Text>
          </Box>
        );
      })}
    </BlockShell>
  );
}

function CodeBlock({ content }: { content: Extract<MessageContent, { type: "code" }> }): React.ReactNode {
  const language = content.language ?? "";
  const [highlighted, setHighlighted] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getHighlighter().then((hl) => {
      if (!hl || cancelled) return;
      try {
        const result = hl(content.code, { language: language || undefined });
        if (!cancelled) setHighlighted(result);
      } catch {
        // Fall back to plain text.
      }
    });
    return () => {
      cancelled = true;
    };
  }, [content.code, language]);

  return (
    <BlockShell title={language ? `Code | ${language}` : "Code"} backgroundColor={CARD_BG_SOFT}>
      {highlighted ? (
        <Box marginLeft={2}>
          <Ansi>{highlighted}</Ansi>
        </Box>
      ) : (
        getStableLineEntries(content.code, `code:${language || "plain"}`).map(({ key, line }) => (
          <Box key={key} marginLeft={2}>
            <Text>{line}</Text>
          </Box>
        ))
      )}
    </BlockShell>
  );
}

function ErrorBlock({ content }: { content: Extract<MessageContent, { type: "error" }> }): React.ReactNode {
  const detailLines = content.details ? getStableLineEntries(content.details, "error-details") : [];

  return (
    <BlockShell title={`Error | ${content.message}`} titleColor="#F07C82" backgroundColor={CARD_BG_ERROR}>
      {detailLines.map(({ key, line }) => (
        <Box key={key} marginLeft={2}>
          <Text color="#F7C4C7" dimColor>{line}</Text>
        </Box>
      ))}
    </BlockShell>
  );
}

const STATUS_ICONS: Record<string, string> = {
  pending: "o",
  in_progress: "~",
  completed: "x",
};

function TaskBlock({ content }: { content: Extract<MessageContent, { type: "task_result" }> }): React.ReactNode {
  const summary = [
    content.counts.pending > 0 ? `${content.counts.pending} pending` : null,
    content.counts.in_progress > 0 ? `${content.counts.in_progress} in progress` : null,
    content.counts.completed > 0 ? `${content.counts.completed} completed` : null,
  ].filter(Boolean).join(" | ");

  return (
    <BlockShell title={summary ? `Tasks | ${summary}` : "Tasks"} backgroundColor={CARD_BG_SOFT}>
      {content.tasks.map((task) => (
        <Box key={task.id} marginLeft={2}>
          <Text>{STATUS_ICONS[task.status] ?? " "}</Text>
          <Text> </Text>
          <Text dimColor={task.status === "completed"}>{task.subject}</Text>
        </Box>
      ))}
    </BlockShell>
  );
}

function PlanBlock({ content }: { content: Extract<MessageContent, { type: "plan" }> }): React.ReactNode {
  const steps = content.steps ?? [];

  return (
    <BlockShell title={`Plan | ${content.summary}`} titleColor="#DA7756" backgroundColor={CARD_BG_SOFT}>
      {steps.map((step, index) => (
        <Box key={`plan-step-${index}`} marginLeft={2} flexDirection="column" marginBottom={1}>
          <Box>
            <Text dimColor>{index + 1}. </Text>
            <Text>{step.step}</Text>
          </Box>
          {step.files && step.files.length > 0 && (
            <Box marginLeft={3}>
              <Text dimColor>files | {step.files.join(", ")}</Text>
            </Box>
          )}
          {step.verification && (
            <Box marginLeft={3}>
              <Text dimColor>verify | {step.verification}</Text>
            </Box>
          )}
        </Box>
      ))}
    </BlockShell>
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
  isActiveSearchHit,
  searchQuery,
}: {
  message: Message;
  renderMessage?: (message: Message) => React.ReactNode;
  allThinkingExpanded?: boolean;
  allToolResultsExpanded?: boolean;
  isActiveSearchHit?: boolean;
  searchQuery?: string;
}): React.ReactNode {
  if (renderMessage) return renderMessage(message);

  const config = ROLE_CONFIG[message.role];
  const isSystem = message.role === "system";
  const searchExcerpt = isActiveSearchHit && searchQuery ? buildSearchExcerpt(message, searchQuery) : null;

  if (typeof message.content === "string") {
    const textLines = getStableLineEntries(message.content, `${message.id}:message`);
    const body = (
      <Box flexDirection="column">
        {textLines.map(({ key, line }) => (
          <Box key={key} marginLeft={2}>
            <Text dimColor={isSystem}>{line}</Text>
          </Box>
        ))}
      </Box>
    );

    return (
      <MessageRail
        color={config.railColor}
        label={
          <Box>
            <Text color={config.color} dimColor={isSystem}>{config.icon}</Text>
            <Text color={config.color} dimColor={isSystem} bold={!isSystem}> {config.label}</Text>
          </Box>
        }
        body={body}
        isActiveSearchHit={isActiveSearchHit}
        searchExcerpt={searchExcerpt}
      />
    );
  }

  const blockKeys = getStableKeys(message.content, getMessageContentFingerprint);
  const body = (
    <Box flexDirection="column">
      {message.content.map((block, index) => (
        <ContentBlock
          key={blockKeys[index]}
          block={block}
          allThinkingExpanded={allThinkingExpanded}
          allToolResultsExpanded={allToolResultsExpanded}
        />
      ))}
    </Box>
  );

  return (
    <MessageRail
      color={config.railColor}
      label={
        <Box>
          <Text color={config.color} dimColor={isSystem}>{config.icon}</Text>
          <Text color={config.color} dimColor={isSystem} bold={!isSystem}> {config.label}</Text>
        </Box>
      }
      body={body}
      isActiveSearchHit={isActiveSearchHit}
      searchExcerpt={searchExcerpt}
    />
  );
}

function LiveReasoningBlock({
  text,
  elapsedMs,
  expanded,
}: {
  text: string;
  elapsedMs?: number;
  expanded?: boolean;
}): React.ReactNode {
  const progressLines = extractProgressLines(text, expanded ? 8 : 4);
  const rawLines = getStableLineEntries(text.slice(-4096), "streaming-thinking");
  const thoughtLabel = formatElapsed(elapsedMs);
  const title = thoughtLabel ? `Thought for ${thoughtLabel}` : "Thinking";
  const fallbackLines = rawLines.map(({ line }) => line.trim()).filter(Boolean).slice(-4);
  const bodyLines = expanded
    ? rawLines.map(({ line }) => line).filter((line) => line.trim())
    : (progressLines.length > 0 ? progressLines : fallbackLines);

  return (
    <BlockShell title={title} backgroundColor={CARD_BG_SOFT}>
      <Box marginBottom={bodyLines.length > 0 ? 1 : 0}>
        <Text dimColor>{expanded ? "Ctrl+T to collapse" : "Ctrl+T to expand live reasoning"}</Text>
      </Box>
      {bodyLines.map((line, index) => (
        <Box key={`live-thinking-${index}`} marginLeft={2}>
          <Text dimColor>{expanded ? line : `- ${line}`}</Text>
        </Box>
      ))}
    </BlockShell>
  );
}

export function MessageList({
  messages,
  streamingContent,
  streamingThinking,
  streamingElapsedMs,
  renderMessage,
  allThinkingExpanded,
  allToolResultsExpanded,
  searchQuery,
  activeSearchMatch,
}: MessageListProps): React.ReactNode {
  const streamingLines = streamingContent ? getStableLineEntries(streamingContent, "streaming") : [];

  return (
    <Box flexDirection="column">
      {messages.map((message, index) => (
        <MessageItem
          key={message.id}
          message={message}
          renderMessage={renderMessage}
          allThinkingExpanded={allThinkingExpanded}
          allToolResultsExpanded={allToolResultsExpanded}
          isActiveSearchHit={activeSearchMatch?.index === index}
          searchQuery={searchQuery}
        />
      ))}

      {streamingThinking && streamingThinking.trim() && (
        <MessageRail
          color={ROLE_CONFIG.assistant.railColor}
          label={
            <Box>
              <Text color={ROLE_CONFIG.assistant.color}>{ROLE_CONFIG.assistant.icon}</Text>
              <Text color={ROLE_CONFIG.assistant.color} bold> Jarvis</Text>
              <Text dimColor> | working</Text>
            </Box>
          }
          body={
            <LiveReasoningBlock
              text={streamingThinking}
              elapsedMs={streamingElapsedMs}
              expanded={allThinkingExpanded}
            />
          }
        />
      )}

      {streamingLines.length > 0 && (
        <MessageRail
          color={ROLE_CONFIG.assistant.railColor}
          label={
            <Box>
              <Text color={ROLE_CONFIG.assistant.color}>{ROLE_CONFIG.assistant.icon}</Text>
              <Text color={ROLE_CONFIG.assistant.color} bold> Jarvis</Text>
              <Text dimColor> | drafting reply</Text>
            </Box>
          }
          body={
            <Box marginLeft={2} flexDirection="column">
              {streamingLines.map(({ key, line }, index) => (
                <Box key={key}>
                  <Text>
                    {line}
                    {index === streamingLines.length - 1 && (
                      <StreamCursor visible streaming color="#DA7756" />
                    )}
                  </Text>
                </Box>
              ))}
            </Box>
          }
        />
      )}
    </Box>
  );
}
