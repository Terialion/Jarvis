/**
 * MessageList — renders streaming content between status bar and input area.
 *
 * Pattern refs:
 * - Codex ReasoningSummaryCell (history_cell.rs:391-452):
 *   dimmed italic, bullet "• " prefix, markdown rendering
 * - Codex UnifiedExecInteractionCell (history_cell.rs:594-651):
 *   "↳ " dim prefix, command in bold, result on "  └ " nested lines
 * - Codex chatwidget.rs: tool call cells with ●/○/✓/✗ status icons
 */
import React, { useState } from "react";
import { Box, Text } from "ink";
import { DiffBlock } from "./DiffBlock.js";
import type { ToolInfo, FileChange } from "../types.js";

interface MessageListProps {
  currentAnswer: string;
  currentThinking: string;
  currentTools: ToolInfo[];
  thinkingExpanded: boolean;
  toolsExpanded: boolean;
  isStreaming: boolean;
  fileChanges?: FileChange[];
}

function toolIcon(status: string): { icon: string; color: string } {
  switch (status) {
    case "running":
      return { icon: "●", color: "yellow" };
    case "ok":
      return { icon: "✓", color: "green" };
    case "error":
      return { icon: "✗", color: "red" };
    default:
      return { icon: "○", color: "gray" };
  }
}

function truncateResult(result: string, maxLen: number = 500): string {
  if (result.length <= maxLen) return result;
  return result.slice(0, maxLen) + `… (${result.length} chars total)`;
}

export const MessageList: React.FC<MessageListProps> = ({
  currentAnswer,
  currentThinking,
  currentTools,
  thinkingExpanded,
  toolsExpanded,
  isStreaming,
  fileChanges,
}) => {
  const hasStreaming = !!(currentAnswer || currentThinking || currentTools.length > 0 || (fileChanges && fileChanges.length > 0));
  const [expandedTools, setExpandedTools] = useState<Record<number, boolean>>({});

  if (!hasStreaming) return null;

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* File changes — inline diff blocks */}
      {fileChanges && fileChanges.length > 0 && (
        <Box flexDirection="column" marginBottom={1}>
          {fileChanges.map((fc, i) => (
            <DiffBlock key={`diff-${i}`} change={fc} />
          ))}
        </Box>
      )}

      {/* Thinking — Codex ReasoningSummaryCell style: bullet prefix, dimmed italic */}
      {currentThinking && thinkingExpanded && (
        <Box flexDirection="column" marginBottom={1}>
          {currentThinking
            .split("\n")
            .filter((line) => line.trim())
            .slice(-40) // show last 40 lines of thinking to avoid flooding
            .map((line, i) => (
              <Text key={i} dimColor italic>
                • {line.length > 280 ? line.slice(-280) : line}
              </Text>
            ))}
          {currentThinking.length > 500 && (
            <Text dimColor>
              {" "}  (showing last ~40 lines · {currentThinking.length} chars total · Ctrl+T to toggle)
            </Text>
          )}
        </Box>
      )}

      {/* Tool calls — Codex style: status icon + display name + args on one line,
          result indented with │ prefix */}
      {currentTools.length > 0 && toolsExpanded && (
        <Box flexDirection="column" marginBottom={1}>
          {currentTools.map((t, i) => {
            const { icon, color } = toolIcon(t.status);
            return (
              <Box key={i} flexDirection="column">
                <Box>
                  <Text color={color}>{icon} </Text>
                  <Text dimColor={t.status === "ok"}>{t.display}</Text>
                  {t.args ? <Text dimColor> {t.args}</Text> : null}
                </Box>
                {t.result ? (
                  <Box flexDirection="column" paddingLeft={2}>
                    {(() => {
                      const collapsed = t.result.length > 500 && !expandedTools[i];
                      const display = collapsed
                        ? t.result.slice(0, 200) + `… (${t.result.length} chars)`
                        : t.result;
                      return (
                        <>
                          <Text dimColor>│ {display}</Text>
                          {t.result.length > 500 && (
                            <Text dimColor>
                              │ {collapsed ? "(expand to view)" : "(collapsed)"}
                            </Text>
                          )}
                        </>
                      );
                    })()}
                  </Box>
                ) : t.status === "running" ? (
                  <Box paddingLeft={2}>
                    <Text dimColor>│ running…</Text>
                  </Box>
                ) : null}
              </Box>
            );
          })}
        </Box>
      )}

      {/* Answer — markdown streaming */}
      {currentAnswer && isStreaming && (
        <Box flexDirection="column">
          {currentAnswer.split("\n").map((line, i) => (
            <Text key={i}>{line}</Text>
          ))}
        </Box>
      )}
    </Box>
  );
};
