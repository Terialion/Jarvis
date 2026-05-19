/**
 * MessageList — renders streaming content between status bar and input area.
 *
 * Codex-style: tool calls shown as inline cells with status icons,
 * thinking text in dimmed/italic block, answer as markdown.
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
  isStreaming: boolean;
}

/** Map status to icon + style — matches Codex's bullet convention. */
function toolIcon(status: string): string {
  switch (status) {
    case "running":
      return "●";
    case "ok":
      return "○";
    case "error":
      return "✗";
    default:
      return "○";
  }
}

export const MessageList: React.FC<MessageListProps> = ({
  currentAnswer,
  currentThinking,
  currentTools,
  thinkingExpanded,
  toolsExpanded,
  isStreaming,
}) => {
  const hasStreaming = !!(currentAnswer || currentThinking || currentTools.length > 0);

  if (!hasStreaming) return null;

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Thinking — dimmed block, Codex's reasoning summary style */}
      {currentThinking && thinkingExpanded && (
        <Box flexDirection="column" marginBottom={1}>
          <Text dimColor color="gray">
            {"  "}💭{" "}
            {currentThinking.length > 500
              ? currentThinking.slice(-500)
              : currentThinking}
          </Text>
        </Box>
      )}

      {/* Tool calls — Codex-style: one line per tool + result on │ prefix */}
      {currentTools.length > 0 && toolsExpanded && (
        <Box flexDirection="column" marginBottom={1}>
          {currentTools.map((t, i) => (
            <Box key={i} flexDirection="column">
              <Text dimColor={t.status === "ok"}>
                {"  "}{toolIcon(t.status)}{" "}
                {t.display}
                {t.args ? ` ${t.args}` : ""}
              </Text>
              {t.result ? (
                <Text dimColor>
                  {"    "}│ {t.result.slice(0, 200)}
                </Text>
              ) : null}
            </Box>
          ))}
        </Box>
      )}

      {/* Answer — only show while streaming; after done, it moves to <Static> */}
      {currentAnswer && isStreaming && <MarkdownRenderer content={currentAnswer} />}
    </Box>
  );
};
