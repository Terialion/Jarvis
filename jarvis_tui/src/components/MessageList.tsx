/**
 * MessageList — renders streaming content between status bar and input area.
 *
 * Completed messages go into <Static> in app.tsx (terminal scrollback).
 * This component only shows current-turn streaming: thinking, tools, answer.
 */
import React from "react";
import { Box, Text } from "ink";
import type { ToolInfo } from "../types.js";
import { MarkdownRenderer } from "./MarkdownRenderer.js";

interface MessageListProps {
  currentAnswer: string;
  currentThinking: string;
  currentTools: ToolInfo[];
  thinkingExpanded: boolean;
  toolsExpanded: boolean;
}

export const MessageList: React.FC<MessageListProps> = ({
  currentAnswer,
  currentThinking,
  currentTools,
  thinkingExpanded,
  toolsExpanded,
}) => {
  const hasStreaming = !!(currentAnswer || currentThinking || currentTools.length > 0);

  if (!hasStreaming) return null;

  return (
    <Box flexDirection="column" paddingX={1}>
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
      {currentAnswer && <MarkdownRenderer content={currentAnswer} />}
    </Box>
  );
};
