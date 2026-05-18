/**
 * MessageItem — renders a single completed message for use inside <Static>.
 * Supports thinking/tools toggles via global state passed from App.
 */
import React from "react";
import { Box, Text } from "ink";
import type { Message } from "../types.js";
import { MarkdownRenderer } from "./MarkdownRenderer.js";

interface MessageItemProps {
  msg: Message;
  thinkingExpanded: boolean;
  toolsExpanded: boolean;
}

export const MessageItem: React.FC<MessageItemProps> = ({
  msg,
  thinkingExpanded,
  toolsExpanded,
}) => (
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
);
