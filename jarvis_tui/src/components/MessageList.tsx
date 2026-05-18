/**
 * MessageList — scrollable message area with flexGrow:1 to fill space
 * between the status bar and input area.
 *
 * Messages that are finalized render statically. The currently-streaming
 * message updates incrementally (Ink handles the diffing).
 */
import React from "react";
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
      {/* Rendered (complete) messages */}
      {messages.map((msg) => (
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
    </Box>
  );
};
