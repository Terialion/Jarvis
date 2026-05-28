import { Box, Text } from "../ink-renderer/index.js";
import type React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getStableKeys } from "./utils/stableKeys";

const FRAMES = ["·", "•", "◦", "•"];
const SPINNER_INTERVAL = 80;
const DEFAULT_COLOR = "#DA7756";
const SHIMMER_PERIOD_MS = 1500;

function useShimmerHex(baseColor: string = DEFAULT_COLOR): string {
  const [brightness, setBrightness] = useState(1);

  useEffect(() => {
    const start = Date.now();
    const id = setInterval(() => {
      const elapsed = (Date.now() - start) % SHIMMER_PERIOD_MS;
      const phase = elapsed / SHIMMER_PERIOD_MS;
      const nextBrightness = 0.6 + 0.4 * Math.sin(phase * Math.PI * 2);
      setBrightness(Math.round(nextBrightness * 100) / 100);
    }, 50);
    return () => clearInterval(id);
  }, []);

  const r = parseInt(baseColor.slice(1, 3), 16);
  const g = parseInt(baseColor.slice(3, 5), 16);
  const b = parseInt(baseColor.slice(5, 7), 16);
  const sr = Math.round(r * brightness).toString(16).padStart(2, "0");
  const sg = Math.round(g * brightness).toString(16).padStart(2, "0");
  const sb = Math.round(b * brightness).toString(16).padStart(2, "0");
  return `#${sr}${sg}${sb}`;
}

function formatElapsed(elapsedMs: number): string {
  const elapsedSeconds = Math.floor(elapsedMs / 1000);
  if (elapsedSeconds < 60) return `${elapsedSeconds}s`;
  return `${Math.floor(elapsedSeconds / 60)}m ${(elapsedSeconds % 60).toString().padStart(2, "0")}s`;
}

function buildIdleHint(elapsedMs: number): string {
  if (elapsedMs < 3_000) return "Waiting for the first streamed update";
  if (elapsedMs < 12_000) return "Model is still preparing the next step";
  if (elapsedMs < 30_000) return "No streamed text yet; this model often batches output";
  return "Still waiting on streamed output or a tool result";
}

export type SpinnerProps = {
  verb?: string;
  fallbackVerbs?: string[];
  color?: string;
  showElapsed?: boolean;
  tokenCount?: number;
  status?: string;
  details?: string[];
  completed?: string[];
  running?: string;
};

export function Spinner({
  verb,
  fallbackVerbs = ["Thinking"],
  color = DEFAULT_COLOR,
  showElapsed = true,
  tokenCount,
  status,
  details = [],
  completed = [],
  running,
}: SpinnerProps): React.ReactNode {
  const [frameIndex, setFrameIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [verbIndex, setVerbIndex] = useState(0);
  const startRef = useRef(Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      setFrameIndex((index) => (index + 1) % FRAMES.length);
      setElapsed(Date.now() - startRef.current);
    }, SPINNER_INTERVAL);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (verb || fallbackVerbs.length <= 1) return;
    const id = setInterval(() => {
      setVerbIndex((index) => (index + 1) % fallbackVerbs.length);
    }, 8000);
    return () => clearInterval(id);
  }, [verb, fallbackVerbs.length]);

  const shimmerColor = useShimmerHex(color);
  const displayVerb = verb || fallbackVerbs[verbIndex % fallbackVerbs.length] || "Thinking";
  const formattedElapsed = formatElapsed(elapsed);
  const formattedTokens = tokenCount && tokenCount > 0
    ? `${tokenCount >= 1000 ? `${(tokenCount / 1000).toFixed(1)}K` : tokenCount} tokens`
    : null;
  const stableCompleted = completed.length > 0 ? getStableKeys(completed, (item) => item) : [];
  const idleHint = useMemo(
    () => (!status && !running && details.length === 0 ? buildIdleHint(elapsed) : null),
    [details.length, elapsed, running, status],
  );

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Text color={shimmerColor}>{FRAMES[frameIndex]}</Text>
        <Text color={color}> {displayVerb}</Text>
        <Text dimColor>...</Text>
        {showElapsed && <Text dimColor>{` (${formattedElapsed})`}</Text>}
        {formattedTokens && <Text dimColor>{` | ${formattedTokens}`}</Text>}
      </Box>

      {status && (
        <Box marginLeft={2}>
          <Text dimColor>{`- ${status}`}</Text>
        </Box>
      )}

      {!status && idleHint && (
        <Box marginLeft={2}>
          <Text dimColor>{`- ${idleHint}`}</Text>
        </Box>
      )}

      {details.map((line, index) => (
        <Box key={`detail-${index}`} marginLeft={2}>
          <Text dimColor>{`- ${line}`}</Text>
        </Box>
      ))}

      {stableCompleted.map((key, index) => (
        <Box key={key} marginLeft={2}>
          <Text color="green">x</Text>
          <Text dimColor>{` ${completed[index]}`}</Text>
        </Box>
      ))}

      {running && (
        <Box marginLeft={2}>
          <Text color={color}>~</Text>
          <Text dimColor>{` ${running}`}</Text>
        </Box>
      )}
    </Box>
  );
}
