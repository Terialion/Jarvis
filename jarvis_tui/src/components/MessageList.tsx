/**
 * MessageList — renders messages between the status bar and input area.
 *
 * Height follows content naturally. When total rows exceed the terminal's
 * available space, the container locks to a fixed viewport with overflow hidden
 * and virtual scrolling kicks in.
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

function estimateMsgRows(msg: Message): number {
  let rows = msg.content.split("\n").length;
  if (msg.thinking) rows += msg.thinking.split("\n").length;
  if (msg.tools) rows += msg.tools.length;
  return rows + 1;
}

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

  // Available rows: terminal height minus chrome (status 1 + toggle 1 + input 3 + footer 1 + safety)
  const availableRows = Math.max(6, (process.stdout.rows ?? 50) - 8);
  const maxOffset = Math.max(0, totalRows - availableRows);
  const clampedOffset = Math.min(scrollOffset, maxOffset);

  // Walk backwards from end to determine which messages are visible
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
  const needsScroll = totalRows > availableRows;

  return (
    <Box
      flexDirection="column"
      height={needsScroll ? availableRows : undefined}
      paddingX={1}
      overflow="hidden"
      justifyContent="flex-end"
    >
      {hiddenAbove > 0 && (
        <Text dimColor>
          ↑ {hiddenAbove} earlier messages (PgUp/PgDn to scroll)
        </Text>
      )}

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
