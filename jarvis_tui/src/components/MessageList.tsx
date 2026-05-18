/**
 * MessageList — message area with flexGrow:1 to fill space between the
 * status bar and input area.
 *
 * Uses justifyContent: "flex-end" so the latest messages sit right above
 * the input area with no gap. Messages that overflow the top are clipped;
 * PgUp/PgDn scroll through history.
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

/** Estimate how many rows a message occupies. */
function estimateMsgRows(msg: Message): number {
  let rows = (msg.content.match(/\n/g) || []).length + 1; // content lines
  if (msg.thinking) rows += (msg.thinking.match(/\n/g) || []).length + 1;
  if (msg.tools) rows += msg.tools.length;
  return rows + 1; // +1 for margin
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
  const hasStreaming = currentAnswer || currentThinking || currentTools.length > 0;

  // Auto-scroll to bottom when new messages arrive or streaming starts
  useEffect(() => {
    setScrollOffset(0);
  }, [messages.length, hasStreaming]);

  // Calculate visible message window
  const availableRows = Math.max(8, (process.stdout.rows ?? 50) - 10);
  let totalRows = 0;
  for (const msg of messages) totalRows += estimateMsgRows(msg);
  if (hasStreaming) totalRows += 3;

  const maxOffset = Math.max(0, totalRows - availableRows);
  const clampedOffset = Math.min(scrollOffset, maxOffset);

  // Walk backwards from the end to find visible messages
  const visible: Message[] = [];
  let rowsFromBottom = 0;
  for (let i = messages.length - 1; i >= 0; i--) {
    const r = estimateMsgRows(messages[i]);
    if (rowsFromBottom + r > availableRows + clampedOffset) break;
    rowsFromBottom += r;
    visible.unshift(messages[i]);
  }

  const hiddenAbove = messages.length - visible.length;

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1} overflow="hidden" justifyContent="flex-end">
      {hiddenAbove > 0 && (
        <Text dimColor>
          ↑ {hiddenAbove} earlier messages (PgUp/PgDn to scroll)
        </Text>
      )}

      {/* Completed messages */}
      {visible.map((msg) => (
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

      {/* Currently-streaming message */}
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

      {/* Scroll indicator when scrolled up */}
      {clampedOffset > 0 && (
        <Text dimColor>↓ scrolled up — PgDn to return to latest</Text>
      )}
    </Box>
  );
};
