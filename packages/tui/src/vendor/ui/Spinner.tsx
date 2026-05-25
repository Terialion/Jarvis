import { Box, Text } from "../ink-renderer/index.js";
import type React from "react";
import { useEffect, useRef, useState } from "react";

const DEFAULT_CHARACTERS =
  process.platform === "darwin" ? ["·", "✢", "✳", "✶", "✻", "✽"] : ["·", "✢", "*", "✶", "✻", "✽"];
const FRAMES = [...DEFAULT_CHARACTERS, ...[...DEFAULT_CHARACTERS].reverse()];
const SPINNER_INTERVAL = 80;
const VERB_ROTATE_INTERVAL = 4000;
const ELAPSED_SHOW_AFTER = 1000;
const DEFAULT_COLOR = "#DA7756";
const TIPS = [
  "Use Ctrl+C twice to exit",
  "Use Esc to interrupt",
  "Type / to see commands",
  "Use Ctrl+T to expand thinking",
];

export type SpinnerProps = {
  label?: string;
  verb?: string;
  verbs?: string[];
  color?: string;
  showElapsed?: boolean;
  /** Token count to display (e.g. "↓ 1.2K tokens") */
  tokenCount?: number;
  /** Tip to show on second line */
  tip?: string;
  /** Detail line below the spinner */
  detail?: string;
};

export function Spinner({
  label,
  verb,
  verbs,
  color = DEFAULT_COLOR,
  showElapsed = true,
  tokenCount,
  tip,
  detail,
}: SpinnerProps): React.ReactNode {
  const [frameIndex, setFrameIndex] = useState(0);
  const [verbIndex, setVerbIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [tipIndex, setTipIndex] = useState(0);
  const startRef = useRef(Date.now());

  const allVerbs = verbs ?? (verb ? [verb] : ["Thinking"]);

  useEffect(() => {
    const id = setInterval(() => {
      setFrameIndex((i) => (i + 1) % FRAMES.length);
      setElapsed(Date.now() - startRef.current);
    }, SPINNER_INTERVAL);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (allVerbs.length <= 1) return;
    const id = setInterval(() => {
      setVerbIndex((i) => (i + 1) % allVerbs.length);
    }, VERB_ROTATE_INTERVAL);
    return () => clearInterval(id);
  }, [allVerbs.length]);

  // Rotate tips every 5s
  useEffect(() => {
    const id = setInterval(() => {
      setTipIndex((i) => (i + 1) % TIPS.length);
    }, 5000);
    return () => clearInterval(id);
  }, []);

  const frame = FRAMES[frameIndex]!;
  const currentVerb = allVerbs[verbIndex % allVerbs.length]!;
  const elapsedSec = Math.floor(elapsed / 1000);
  const showTime = showElapsed && elapsed >= ELAPSED_SHOW_AFTER;

  const fmtElapsed = elapsedSec < 60
    ? `${elapsedSec}s`
    : `${Math.floor(elapsedSec / 60)}m ${(elapsedSec % 60).toString().padStart(2, '0')}s`;

  const fmtTokens = tokenCount && tokenCount > 0
    ? `↓ ${tokenCount >= 1000 ? (tokenCount / 1000).toFixed(1) + 'K' : tokenCount} tokens`
    : null;

  return (
    <Box flexDirection="column" marginTop={1}>
      <Box>
        <Text color={color}>{frame}</Text>
        <Text> {currentVerb}</Text>
        {label && <Text> {label}</Text>}
        <Text dimColor> (</Text>
        <Text dimColor>{fmtElapsed}</Text>
        {fmtTokens && (
          <>
            <Text dimColor> · </Text>
            <Text dimColor>{fmtTokens}</Text>
          </>
        )}
        <Text dimColor>)</Text>
      </Box>
      {detail && (
        <Box marginLeft={1}>
          <Text dimColor>  └  {detail}</Text>
        </Box>
      )}
      {!detail && (tip ?? TIPS[tipIndex % TIPS.length]) && (
        <Box marginLeft={1}>
          <Text dimColor>  ⎿  Tip: {tip ?? TIPS[tipIndex % TIPS.length]}</Text>
        </Box>
      )}
    </Box>
  );
}
