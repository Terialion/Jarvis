/**
 * StatusBar — Claude Code style clean status row.
 *
 * Pattern: spinner + "Working · 32s · ↓ 1.2k tokens" (left) + model (right).
 * No borders, no heavy separators.
 */
import React from "react";
import { Box, Text } from "ink";
import { Spinner } from "./Spinner.js";
import { ShimmerText } from "./ShimmerText.js";

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
  contextUsed?: number;
  contextWindow?: number;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  modelName,
  latency,
  tokenCount,
  cost,
  isStreaming,
  activeTool,
  activeAgents = 0,
  contextUsed = 0,
  contextWindow = 0,
}) => {
  // Build suffix segments (everything after "Working")
  const suffixParts: string[] = [];
  if (isStreaming) {
    if (activeTool) suffixParts.push(activeTool);
    suffixParts.push(latency || "...");
    if (tokenCount > 0) suffixParts.push(`↓ ${formatTokens(tokenCount)} tokens`);
    if (activeAgents > 0) suffixParts.push(`${activeAgents} agents`);
  } else if (latency) {
    suffixParts.push(latency);
    if (tokenCount > 0) suffixParts.push(`↓ ${formatTokens(tokenCount)} tokens`);
  }
  const suffix = suffixParts.join(" · ");

  return (
    <Box height={1} flexShrink={0} justifyContent="space-between">
      <Box>
        {isStreaming ? (
          <>
            <Spinner visible />
            <ShimmerText text="Working" />
            {suffix ? <Text dimColor> · {suffix}</Text> : null}
          </>
        ) : suffix ? (
          <Text dimColor>{suffix}</Text>
        ) : null}
      </Box>
      <Text dimColor>
        {modelName}
        {contextWindow > 0 ? ` · ${formatTokens(contextUsed)}/${formatTokens(contextWindow)}` : ""}
        {cost > 0 ? ` · $${cost.toFixed(4)}` : ""}
      </Text>
    </Box>
  );
};
