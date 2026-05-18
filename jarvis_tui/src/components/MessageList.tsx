/**
 * MessageList — renders messages between the status bar and input area.
 *
 * Virtual scrolling: calculates which messages fit in the available space
 * (accounting for the current streaming content height). PgUp/PgDn navigate
 * through history. justifyContent: "flex-end" keeps the latest content
 * right above the input area.
 */
import React, { useEffect } from "react";
import { Box, Text } from "ink";
import type { Message, ToolInfo } from "../types.js";
import { MarkdownRenderer } from "./MarkdownRenderer.js";

interface MessageListProps {
  messages: Message[];
  currentAnswer: string;
  currentThinking: string;
  currentTools: ToolInfo[];
  thinkingExpanded: boolean;
  toolsExpanded: boolean;
  scrollOffset: number;
  setScrollOffset: React.Dispatch<React.SetStateAction<number>>;
}

/** Estimate how many terminal rows a completed message occupies. */
function estimateMsgRows(msg: Message): number {
  let rows = msg.content.split("\n").length;
  if (msg.thinking) rows += msg.thinking.split("\n").length;
  if (msg.tools) rows += msg.tools.length;
  return rows + 1; // +1 for margin
}

/** Estimate how many rows the streaming content occupies. */
function estimateStreamingRows(
  answer: string,
  thinking: string,
  tools: ToolInfo[],
  thinkingExpanded: boolean,
  toolsExpanded: boolean,
): number {
  let rows = 0;
  if (answer) rows += answer.split("\n").length;
  if (thinking && thinkingExpanded) rows += thinking.split("\n").length;
  if (tools.length > 0 && toolsExpanded) rows += tools.length;
  return rows;
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  currentAnswer,
  currentThinking,
  currentTools,
  thinkingExpanded,
  toolsExpanded,
  scrollOffset,
  setScrollOffset,
}) => {
  const hasStreaming = !!(currentAnswer || currentThinking || currentTools.length > 0);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    setScrollOffset(0);
  }, [messages.length]);

  // Calculate total content height
  let totalRows = 0;
  for (const msg of messages) totalRows += estimateMsgRows(msg);
  if (hasStreaming) {
    totalRows += estimateStreamingRows(
      currentAnswer, currentThinking, currentTools,
      thinkingExpanded, toolsExpanded,
    );
  }

  const availableRows = Math.max(8, (process.stdout.rows ?? 50) - 8);
  const maxOffset = Math.max(0, totalRows - availableRows);
  const clampedOffset = Math.min(scrollOffset, maxOffset);

  // Walk backwards from end to find visible completed messages.
  // Streaming content is always visible at the bottom.
  let rowsFromBottom = hasStreaming
    ? estimateStreamingRows(
        currentAnswer, currentThinking, currentTools,
        thinkingExpanded, toolsExpanded,
      )
    : 0;
  const visibleMessages: Message[] = [];

  for (let i = messages.length - 1; i >= 0; i--) {
    const r = estimateMsgRows(messages[i]);
    if (rowsFromBottom + r > availableRows + clampedOffset) break;
    rowsFromBottom += r;
    visibleMessages.unshift(messages[i]);
  }

  const hiddenAbove = messages.length - visibleMessages.length;

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1} overflow="hidden" justifyContent="flex-end">
      {hiddenAbove > 0 && (
        <Text dimColor>
          ↑ {hiddenAbove} earlier messages (PgUp/PgDn to scroll)
        </Text>
      )}

      {/* Completed messages */}
      {visibleMessages.map((msg) => (
        <Box key={msg.id} flexDirection="column" marginBottom={1}>
          {msg.role === "user" ? (
            <Text dimColor>❯ {msg.content}</Text>
          ) : (
            <MarkdownRenderer content={msg.content} />
          )}
          {msg.thinking && thinkingExpanded && (
            <Text dimColor color="gray">
              {"  ".repeat(2)}💭 {msg.thinking}
            </Text>
          )}
          {msg.tools && toolsExpanded && (
            <Box flexDirection="column">
              {msg.tools.map((t, i) => (
                <Text key={i} dimColor>
                  {"  ".repeat(2)}● {t.display} {t.args}
                </Text>
              ))}
            </Box>
          )}
        </Box>
      ))}

      {/* Current streaming content */}
      {hasStreaming && (
        <Box flexDirection="column">
          {currentThinking && thinkingExpanded && (
            <Text dimColor color="gray">
              {"  ".repeat(2)}💭 {currentThinking}
            </Text>
          )}
          {currentTools.length > 0 && toolsExpanded && (
            <Box flexDirection="column" marginBottom={1}>
              {currentTools.map((t, i) => (
                <Text key={i} dimColor>
                  {"  ".repeat(2)}● {t.display} {t.args}
                </Text>
              ))}
            </Box>
          )}
          {currentAnswer && <Text>{currentAnswer}</Text>}
        </Box>
      )}

      {/* Scroll indicator */}
      {clampedOffset > 0 && (
        <Text dimColor>↓ scrolled up — PgDn to return to latest</Text>
      )}
    </Box>
  );
};
