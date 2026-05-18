/**
 * MessageList — renders the current streaming content in the dynamic area.
 * Completed messages are rendered by <Static> in App, outside this component.
 *
 * Uses flexGrow:1 + justifyContent:"flex-end" so the streaming content sits
 * right above the input area with no gap.
 */
import React from "react";
import { Box, Text } from "ink";
import type { ToolInfo } from "../types.js";

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
  const hasStreaming = currentAnswer || currentThinking || currentTools.length > 0;

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1} overflow="hidden" justifyContent="flex-end">
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
