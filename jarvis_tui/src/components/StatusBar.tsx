/**
 * StatusBar — top bar showing Jarvis version, model, working directory,
 * plus runtime info (latency, cost, permission mode) during streaming.
 */
import React from "react";
import { Box, Text } from "ink";
import { readFileSync } from "node:fs";

// Lazy-load version from package.json
let _version = "";
function getVersion(): string {
  if (_version) return _version;
  try {
    const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
    _version = pkg.version ?? "0.0.0";
  } catch {
    _version = "0.0.0";
  }
  return _version;
}

interface StatusBarProps {
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
  modelName,
  projectRoot,
  gitBranch,
  latency,
  tokenCount,
  cost,
  permissionMode,
  isStreaming,
}) => {
  const version = getVersion();
  const parts: string[] = [];
  parts.push(modelName);
  parts.push(projectRoot);

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
        {"─".repeat(4)} Jarvis v{version} · {parts.join(" · ")}
      </Text>
    </Box>
  );
};
