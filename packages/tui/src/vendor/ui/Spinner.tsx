import { Box, Text } from "../ink-renderer/index.js";
import type React from "react";
import { useEffect, useRef, useState } from "react";
import { getStableKeys } from "./utils/stableKeys";

const DEFAULT_CHARACTERS =
  process.platform === "darwin" ? ["·", "✢", "✳", "✶", "✻", "✽"] : ["·", "✢", "*", "✶", "✻", "✽"];
const FRAMES = [...DEFAULT_CHARACTERS, ...[...DEFAULT_CHARACTERS].reverse()];
const SPINNER_INTERVAL = 80;
const DEFAULT_COLOR = "#DA7756";

export type SpinnerProps = {
  /** Dynamic verb/description — from reasoning or current action */
  verb?: string;
  /** Fallback verbs for rotation when no dynamic verb */
  fallbackVerbs?: string[];
  color?: string;
  showElapsed?: boolean;
  /** Token count (e.g. "↓ 1.2K tokens") */
  tokenCount?: number;
  /** Status suffix (e.g. "almost done thinking with high effort") */
  status?: string;
  /** Completed tool names to show as ✔ checkmarks */
  completed?: string[];
  /** Running tool name to show as ◌ */
  running?: string;
};

export function Spinner({
  verb,
  fallbackVerbs = ["Thinking"],
  color = DEFAULT_COLOR,
  showElapsed = true,
  tokenCount,
  status,
  completed = [],
  running,
}: SpinnerProps): React.ReactNode {
  const [frameIndex, setFrameIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [verbIdx, setVerbIdx] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      setFrameIndex((i) => (i + 1) % FRAMES.length);
      setElapsed(Date.now() - startRef.current);
    }, SPINNER_INTERVAL);
    return () => clearInterval(id);
  }, []);

  // Rotate fallback verbs every 8s when no dynamic verb
  useEffect(() => {
    if (verb || fallbackVerbs.length <= 1) return;
    const id = setInterval(() => {
      setVerbIdx((i) => (i + 1) % fallbackVerbs.length);
    }, 8000);
    return () => clearInterval(id);
  }, [verb, fallbackVerbs.length]);

  const elapsedMs = elapsed;
  const elapsedSec = Math.floor(elapsedMs / 1000);
  const fmtElapsed = elapsedSec < 60
    ? `${elapsedSec}s`
    : `${Math.floor(elapsedSec / 60)}m ${(elapsedSec % 60).toString().padStart(2, '0')}s`;

  const fmtTokens = tokenCount && tokenCount > 0
    ? `↓ ${tokenCount >= 1000 ? (tokenCount / 1000).toFixed(1) + 'K' : tokenCount} tokens`
    : null;

  // Use dynamic verb if provided, otherwise rotate fallback
  const displayVerb = verb || fallbackVerbs[verbIdx % fallbackVerbs.length]!;
  const frame = FRAMES[frameIndex]!;

  // Show "thought for Ns" when reasoning ends and content generation begins
  const statusText = status || (verb && elapsedSec > 0 && !running
    ? `thought for ${elapsedSec < 5 ? `${Math.floor(elapsedMs / 100) / 10}s` : fmtElapsed}`
    : undefined);

  const stableCompleted = completed.length > 0
    ? getStableKeys(completed, (t) => t)
    : [];

  return (
    <Box flexDirection="column" marginTop={1}>
      {/* Main line: spinner + verb + stats */}
      <Box>
        <Text color={color}>{frame}</Text>
        <Text> {displayVerb}</Text>
        {!verb && <Text>...</Text>}
        {verb && <Text dimColor>…</Text>}
        <Text> </Text>
        <Text dimColor>(</Text>
        <Text dimColor>{fmtElapsed}</Text>
        {fmtTokens && (
          <>
            <Text dimColor> · </Text>
            <Text dimColor>{fmtTokens}</Text>
          </>
        )}
        {statusText && (
          <>
            <Text dimColor> · </Text>
            <Text dimColor>{statusText}</Text>
          </>
        )}
        <Text dimColor>)</Text>
      </Box>

      {/* Completed tool checkmarks */}
      {stableCompleted.map((key, i) => (
        <Box key={key} marginLeft={2}>
          <Text dimColor>  ⎿  </Text>
          <Text color="green">✔</Text>
          <Text dimColor> {completed[i]}</Text>
        </Box>
      ))}

      {/* Currently running tool */}
      {running && (
        <Box marginLeft={2}>
          <Text dimColor>  ⎿  </Text>
          <Text dimColor>◌ {running}</Text>
        </Box>
      )}
    </Box>
  );
}
