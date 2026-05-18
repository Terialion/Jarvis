/**
 * MessageList — message area with flexGrow:1 to fill space between the
 * status bar and input area.
 *
 * Completed messages render via Ink's <Static> component — they accumulate
 * in the terminal's scrollback buffer (like normal terminal output). Only
 * the currently-streaming content participates in Yoga's dynamic layout.
 */
import React from "react";
import { Box, Text, Static } from "ink";
import type { Message, ToolInfo } from "../types.js";
import { MarkdownRenderer } from "./MarkdownRenderer.js";

interface MessageListProps {
  messages: Message[];
  currentAnswer: string;
  currentThinking: string;
  currentTools: ToolInfo[];
  thinkingExpanded: boolean;
  toolsExpanded: boolean;
}

function renderMessage(msg: Message, _index: number): React.ReactNode {
  return (
    <Box key={msg.id} flexDirection="column" marginBottom={1}>
      {msg.role === "user" ? (
        <Text dimColor>❯ {msg.content}</Text>
      ) : (
        <MarkdownRenderer content={msg.content} />
      )}
      {msg.thinking && (
        <Text dimColor color="gray">
          {"  ".repeat(2)}{msg.thinking}
        </Text>
      )}
    </Box>
  );
}

export const MessageList: React.FC<MessageListProps> = ({
  messages,
  currentAnswer,
  currentThinking,
  currentTools,
  thinkingExpanded,
  toolsExpanded,
}) => {
  const hasStreaming = currentAnswer || currentThinking || currentTools.length > 0;

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1} overflow="hidden">
      {/* Completed messages — rendered once, persist in terminal scrollback */}
      <Static items={messages}>{renderMessage}</Static>

      {/* Currently-streaming message — dynamic, updates in place */}
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
    </Box>
  );
};
