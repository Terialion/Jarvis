import { Ansi, Box, type Color, stringWidth, TerminalSizeContext, Text } from "../ink-renderer/index.js";
import React, { useEffect, useState } from "react";
import { useContext } from "react";
import { getStableKeys } from "./utils/stableKeys";

export type StatusLineSegment = {
  content: string;
  color?: Color;
  flex?: boolean;
};

export type StatusLineProps = {
  segments?: StatusLineSegment[];
  text?: string;
  paddingX?: number;
  /** @deprecated Use separator instead. Gap between segments in columns. */
  gap?: number;
  /** Separator string between segments (default: ' | ') */
  separator?: string;
  borderStyle?: "none" | "single" | "round";
  borderColor?: Color;
};

const ANSI_ESCAPE = new RegExp(`${String.fromCharCode(0x1b)}\\[`);
function hasAnsi(s: string): boolean {
  return ANSI_ESCAPE.test(s);
}

function truncatePlainText(value: string, maxWidth: number): string {
  if (maxWidth <= 0) return "";
  if (stringWidth(value) <= maxWidth) return value;
  if (maxWidth === 1) return ".";

  let out = "";
  for (const char of value) {
    const next = out + char;
    if (stringWidth(next) >= maxWidth) break;
    out = next;
  }
  return `${out}...`;
}

function truncateSegmentContent(value: string, maxWidth: number): string {
  if (maxWidth <= 0) return "";
  if (stringWidth(value) <= maxWidth) return value;
  if (maxWidth === 1) return ".";

  let out = "";
  for (const char of value) {
    const next = out + char;
    if (stringWidth(next) >= maxWidth) break;
    out = next;
  }
  return `${out}...`;
}

function truncateSegments(
  segments: StatusLineSegment[],
  separator: string,
  maxWidth: number,
): StatusLineSegment[] {
  if (maxWidth <= 0) return [];
  const result: StatusLineSegment[] = [];
  const separatorWidth = stringWidth(separator);
  let usedWidth = 0;

  for (const segment of segments) {
    const needsSeparator = result.length > 0;
    const reserved = needsSeparator ? separatorWidth : 0;
    const remaining = maxWidth - usedWidth - reserved;
    if (remaining <= 0) break;

    const contentWidth = stringWidth(segment.content);
    if (needsSeparator) usedWidth += separatorWidth;

    if (contentWidth <= remaining) {
      result.push(segment);
      usedWidth += contentWidth;
      continue;
    }

    result.push({
      ...segment,
      content: truncateSegmentContent(segment.content, remaining),
      flex: false,
    });
    break;
  }

  return result;
}

export function StatusLine({
  segments,
  text,
  paddingX = 1,
  separator = " | ",
  borderStyle = "none",
  borderColor,
}: StatusLineProps): React.ReactNode {
  const terminalSize = useContext(TerminalSizeContext);
  const border = borderStyle === "none" ? undefined : borderStyle;
  const availableWidth = Math.max(1, (terminalSize?.columns ?? 80) - paddingX * 2);
  const plainText = text ?? segments?.map((seg) => seg.content).join(separator) ?? "";
  const canRenderAsSinglePlainLine = text !== undefined && !hasAnsi(plainText);
  const segmentKeys = segments
    ? getStableKeys(
        segments,
        (seg) => `${seg.content}:${seg.color ?? "default"}:${seg.flex ? "flex" : "fixed"}`,
      )
    : [];
  const truncatedSegments =
    text === undefined && segments && segments.every((seg) => !hasAnsi(seg.content))
      ? truncateSegments(segments, separator, availableWidth)
      : segments;

  return (
    <Box flexDirection="row" paddingX={paddingX} borderStyle={border} borderColor={borderColor}>
      {canRenderAsSinglePlainLine ? (
        <Text dimColor>{truncatePlainText(plainText, availableWidth)}</Text>
      ) : text !== undefined ? (
        hasAnsi(text) ? (
          <Ansi>{text}</Ansi>
        ) : (
          <Text dimColor>{text}</Text>
        )
      ) : (
        truncatedSegments?.map((seg, i) => (
          <React.Fragment key={segmentKeys[i]}>
            {i > 0 && <Text dimColor>{separator}</Text>}
            <Box flexGrow={seg.flex ? 1 : 0}>
              {hasAnsi(seg.content) ? (
                <Ansi>{seg.content}</Ansi>
              ) : (
                <Text dimColor color={seg.color}>
                  {seg.content}
                </Text>
              )}
            </Box>
          </React.Fragment>
        ))
      )}
    </Box>
  );
}

export function useStatusLine(
  updater: () => StatusLineSegment[] | string,
  deps: unknown[],
  intervalMs?: number,
): StatusLineSegment[] | string {
  const [value, setValue] = useState<StatusLineSegment[] | string>(() => updater());

  useEffect(() => {
    setValue(updater());
    // biome-ignore lint/correctness/useExhaustiveDependencies: deps are intentionally dynamic
  }, deps);

  useEffect(() => {
    if (!intervalMs) return;
    const id = setInterval(() => setValue(updater()), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs, updater]);

  return value;
}

