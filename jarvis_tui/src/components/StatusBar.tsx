/**
 * StatusBar — fixed top bar showing model, git branch, latency, cost, permission mode.
 * Mimics Claude Code's top status line.
 */
import React from "react";
import { Box, Text } from "ink";

interface StatusBarProps {
  modelName: string;
  gitBranch: string;
  latency: string;
  tokenCount: number;
  cost: number;
  permissionMode: string;
  isStreaming: boolean;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  modelName,
  gitBranch,
  latency,
  tokenCount,
  cost,
  permissionMode,
  isStreaming,
}) => {
  const parts: string[] = [];
  parts.push(modelName);

  if (gitBranch) parts.push(gitBranch);

  if (isStreaming && latency) {
    parts.push(`● ${latency}`);
  } else if (latency) {
    parts.push(latency);
  }

  if (permissionMode && permissionMode !== "default") {
    parts.push(`[${permissionMode}]`);
  }

  if (cost > 0) {
    parts.push(`$${cost.toFixed(4)}`);
  }

  return (
    <Box height={1} flexShrink={0}>
      <Text dimColor>
        {"─".repeat(4)} Jarvis{" "}
        {parts.join(" · ")}
      </Text>
    </Box>
  );
};
