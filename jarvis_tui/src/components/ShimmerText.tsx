/**
 * ShimmerText — Codex-style shimmer animation for streaming text.
 *
 * Implements the same sweep algorithm as Codex shimmer.rs:
 * - Time-driven band sweep (2s period)
 * - Cosine interpolation for smooth falloff
 * - 5-char band half-width with 10-char padding
 * - True-color RGB blending with dim/bold fallback
 *
 * Performance: renders per-character spans. Keep usage to short
 * header text (< 200 chars). For the streaming answer, only the
 * last line passes through here.
 */
import React, { useState, useEffect } from "react";
import { Text } from "ink";

const SWEEP_SECONDS = 2.0;
const BAND_HALF_WIDTH = 5;
const PADDING = 10;
const INTERVAL_MS = 50;

/** Cosine interpolation: peak at dist=0, zero at dist >= band_half_width */
function shimmerIntensity(dist: number): number {
  if (dist >= BAND_HALF_WIDTH) return 0;
  return 0.5 * (1.0 + Math.cos(Math.PI * (dist / BAND_HALF_WIDTH)));
}

/** Blend two RGB colors by factor t (0=base, 1=highlight). */
function blendRgb(
  base: [number, number, number],
  highlight: [number, number, number],
  t: number,
): [number, number, number] {
  return [
    Math.round(base[0] + (highlight[0] - base[0]) * t),
    Math.round(base[1] + (highlight[1] - base[1]) * t),
    Math.round(base[2] + (highlight[2] - base[2]) * t),
  ];
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
}

interface ShimmerTextProps {
  text: string;
  /** Use dim/bold fallback instead of RGB blending (no-color terminals). */
  noColor?: boolean;
}

export const ShimmerText: React.FC<ShimmerTextProps> = ({
  text,
  noColor = false,
}) => {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      setElapsed((prev) => prev + INTERVAL_MS);
    }, INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  if (!text) return null;

  const chars = [...text];
  const period = chars.length + PADDING * 2;
  const posF =
    ((elapsed / 1000) % SWEEP_SECONDS) / SWEEP_SECONDS * period;
  const pos = posF;

  // Base: dim gray, Highlight: near-white
  const baseRgb: [number, number, number] = [128, 128, 128];
  const highlightRgb: [number, number, number] = [240, 240, 240];

  return (
    <Text>
      {chars.map((ch, i) => {
        const iPos = i + PADDING;
        const dist = Math.abs(iPos - pos);
        const t = shimmerIntensity(dist);

        if (noColor) {
          // Fallback: use bold for highlight band, dim for base
          if (t > 0.5) return <Text key={i} bold>{ch}</Text>;
          if (t > 0.1) return <Text key={i}>{ch}</Text>;
          return <Text key={i} dimColor>{ch}</Text>;
        }

        const highlight = t;
        const [r, g, b] = blendRgb(baseRgb, highlightRgb, highlight * 0.9);
        return (
          <Text key={i} color={rgbToHex(r, g, b)}>
            {ch}
          </Text>
        );
      })}
    </Text>
  );
};
