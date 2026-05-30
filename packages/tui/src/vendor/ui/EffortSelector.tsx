import { Box, TerminalSizeContext, Text, type Key, useInput } from "../ink-renderer/index.js";
import type React from "react";
import { useCallback, useContext, useRef, useState } from "react";

// ============================================================================
export type EffortSelectorProps = {
  currentEffort: string;
  levels: readonly string[];
  onSelect: (effort: string) => void;
  onCancel: () => void;
  onChange?: (effort: string) => void;
};

// ============================================================================
const LABELS: Record<string, string> = {
  auto: "Auto", minimal: "Minimal", low: "Low", medium: "Medium",
  high: "High", xhigh: "X-High", max: "Max",
};
const labelOf = (e: string) => LABELS[e] ?? e;

const GRADIENT = ["#E5C07B", "#98C379", "#56B6C2", "#61AFEF", "#C678DD", "#E06C75"];
function gradColor(i: number, n: number): string {
  if (n <= 1) return GRADIENT[0]!;
  return GRADIENT[Math.min(Math.floor((i / (n - 1)) * (GRADIENT.length - 1)), GRADIENT.length - 1)]!;
}

// ============================================================================
export function EffortSelector({
  currentEffort, levels, onSelect, onCancel, onChange,
}: EffortSelectorProps): React.ReactNode {
  const ci = Math.max(0, levels.indexOf(currentEffort));
  const [idx, setIdx] = useState(ci);
  const idxRef = useRef(ci);
  const doneRef = useRef(false);

  const clamp = (v: number) => Math.max(0, Math.min(levels.length - 1, v));
  const move = useCallback((d: number) => {
    idxRef.current = clamp(idxRef.current + d);
    setIdx(idxRef.current);
    onChange?.(levels[idxRef.current]!);
  }, [levels, onChange]);

  useInput((_input: string, key: Key) => {
    if (doneRef.current) return;
    if (key.escape) { doneRef.current = true; onCancel(); return; }
    if (key.return) { doneRef.current = true; onSelect(levels[idxRef.current]!); return; }
    if (key.leftArrow || _input === "h") { move(-1); return; }
    if (key.rightArrow || _input === "l") { move(1); return; }
  }, { isActive: true });

  const term = useContext(TerminalSizeContext);
  const tw = term?.columns ?? 80;
  const sel = levels[idxRef.current]!;
  const isAuto = sel === "auto";
  const spectrum = levels.filter((l) => l !== "auto");
  const m = spectrum.length;
  const autoIdx = idxRef.current;

  // --- Layout ---
  // Row 1: "Faster" ... "Smarter"
  // Row 2: "(○/●) Auto" + bar; bar is fixed ~46 chars, centered
  // Row 3: labels under bar
  // Row 4: selected description (if not auto)
  const HEAD_L = "Faster";
  const HEAD_R = "Smarter";

  // Bar dimensions
  const BAR_W = Math.min(50, tw - 22); // ~50 chars wide, not full width
  const colW = Math.floor(BAR_W / m);

  // Circle + Auto prefix
  const autoPrefix = isAuto ? " ● Auto  " : " ○ Auto  ";
  const prefixLen = autoPrefix.length; // 9

  // --- Build bar ---
  let bar = "";
  for (let i = 0; i < m; i++) {
    const segCenter = i * colW + Math.floor(colW / 2);
    for (let j = i * colW; j < (i + 1) * colW && j < BAR_W; j++) {
      bar += (!isAuto && i === (autoIdx - 1) && j === segCenter) ? "▲" : "─";
    }
  }
  // When Auto is selected, no ▲ — the arrow is "off the bar"

  // --- Build label positions ---
  const labelStarts: number[] = [];
  let lCursor = 0;
  for (let i = 0; i < m; i++) {
    const txt = labelOf(spectrum[i]!);
    const segCenter = i * colW + Math.floor(colW / 2);
    let s = segCenter - Math.floor(txt.length / 2);
    if (s < lCursor) s = lCursor + 1;
    labelStarts.push(s);
    lCursor = s + txt.length;
  }

  // --- Header: "Faster" + gap + "Smarter" ---
  const headerW = prefixLen + BAR_W;
  const headerPad = headerW - HEAD_L.length - HEAD_R.length;
  const headerLine = HEAD_L + " ".repeat(Math.max(1, headerPad)) + HEAD_R;

  // --- Label row: individual Text elements for per-label coloring ---
  const labelRow: React.ReactNode[] = [];
  // Prefix padding
  labelRow.push(<Text key="lp">{" ".repeat(prefixLen)}</Text>);
  let lEnd = prefixLen;
  for (let i = 0; i < m; i++) {
    const s = labelStarts[i]! + prefixLen; // shift into full-line coordinates
    const txt = labelOf(spectrum[i]!);
    const active = !isAuto && i === (autoIdx - 1);
    const gap = Math.max(0, s - lEnd);
    if (gap > 0) labelRow.push(<Text key={`lg-${i}`}>{" ".repeat(gap)}</Text>);
    if (active) {
      labelRow.push(<Text key={i} color={gradColor(i, m)} bold>{txt}</Text>);
    } else {
      labelRow.push(<Text key={i} dimColor>{txt}</Text>);
    }
    lEnd = s + txt.length;
  }

  return (
    <Box flexDirection="column" paddingX={2} paddingY={1}>
      <Box marginBottom={1}>
        <Text bold color="cyan">Effort</Text>
      </Box>

      {/* Faster / Smarter header */}
      <Box marginBottom={1}>
        <Text dimColor>{headerLine}</Text>
      </Box>

      {/* Bar + labels */}
      <Box flexDirection="column" marginBottom={1}>
        <Text>{autoPrefix + bar}</Text>
        <Box flexDirection="row">{labelRow}</Box>
      </Box>

      {/* Current effort */}
      <Box marginBottom={1}>
        <Text dimColor>
          Current: {labelOf(currentEffort)}
        </Text>
      </Box>

      {/* Footer */}
      <Box>
        <Text dimColor>←/→ to adjust · Enter to confirm · Esc to cancel</Text>
      </Box>
    </Box>
  );
}
