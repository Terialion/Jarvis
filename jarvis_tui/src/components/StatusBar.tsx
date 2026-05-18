/**
 * StatusBar — top bar showing Jarvis version, model, working directory,
 * plus runtime info (latency, token count, cost, permission mode).
 */
import React from "react";
import { Box, Text } from "ink";

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

interface StatusBarProps {
  version: string;
  modelName: string;
  projectRoot: string;
  gitBranch: string;
  latency: string;
  tokenCount: number;
  cost: number;
  permissionMode: string;
  isStreaming: boolean;
}

export const StatusBar: React.FC<StatusBarProps> = ({
  version,
  modelName,
  projectRoot,
  gitBranch,
  latency,
  tokenCount,
  cost,
  permissionMode,
  isStreaming,
}) => {

  // Build runtime info segment (shown during/after streaming)
  const runtime: string[] = [];
  if (isStreaming && latency) {
    runtime.push(`Thinking… (${latency}`);
    if (tokenCount > 0) runtime.push(`↓ ${formatTokens(tokenCount)} tokens`);
    runtime.push(")");
  } else if (latency) {
    runtime.push(latency);
    if (tokenCount > 0) runtime.push(`↓ ${formatTokens(tokenCount)} tokens`);
  }
  if (permissionMode && permissionMode !== "default") {
    runtime.push(`[${permissionMode}]`);
  }
  if (cost > 0) {
    runtime.push(`$${cost.toFixed(4)}`);
  }

  const line = [
    modelName,
    projectRoot,
    ...runtime,
  ].filter(Boolean).join(" · ");

  return (
    <Box height={1} flexShrink={0}>
      <Text dimColor>
        {"─".repeat(4)} Jarvis v{version} · {line}
      </Text>
    </Box>
  );
};
