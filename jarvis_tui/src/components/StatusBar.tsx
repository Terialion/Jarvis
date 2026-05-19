/**
 * StatusBar — Claude Code style clean status row.
 *
 * Pattern: spinner + "Working · 32s · ↓ 1.2k tokens" (left) + model (right).
 * No borders, no heavy separators.
 */
import React from "react";
import { Box, Text } from "ink";
import { Spinner } from "./Spinner.js";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

interface StatusBarProps {
  modelName: string;
  latency: string;
  tokenCount: number;
  cost: number;
  isStreaming: boolean;
  activeTool?: string;
  activeAgents?: number;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  modelName,
  latency,
  tokenCount,
  cost,
  isStreaming,
  activeTool,
  activeAgents = 0,
}) => {
  const segments: string[] = [];

  if (isStreaming) {
    segments.push("Working");
    if (activeTool) segments.push(activeTool);
    segments.push(latency || "...");
    if (tokenCount > 0) segments.push(`↓ ${formatTokens(tokenCount)} tokens`);
    if (activeAgents > 0) segments.push(`${activeAgents} agents`);
  } else if (latency) {
    segments.push(latency);
    if (tokenCount > 0) segments.push(`↓ ${formatTokens(tokenCount)} tokens`);
  }

  return (
    <Box height={1} flexShrink={0} justifyContent="space-between">
      <Box>
        {isStreaming ? (
          <>
            <Spinner visible />
            <Text> </Text>
          </>
        ) : (
          <Text> </Text>
        )}
        <Text dimColor>{segments.join(" · ")}</Text>
      </Box>
      <Text dimColor>
        {modelName}
        {cost > 0 ? ` · $${cost.toFixed(4)}` : ""}
      </Text>
    </Box>
  );
};
