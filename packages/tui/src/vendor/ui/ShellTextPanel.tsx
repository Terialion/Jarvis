import { Box, ScrollBox, Text, type Key, useInput, type ScrollBoxHandle } from "../ink-renderer/index.js";
import type React from "react";
import { useCallback, useMemo, useRef, useState } from "react";

export type ShellTextPanelProps = {
  title: string;
  subtitle?: string;
  lines: string[];
  accentColor?: "cyan" | "yellow" | "green" | "red" | "gray";
  onClose: () => void;
};

export function ShellTextPanel({
  title,
  subtitle,
  lines,
  accentColor = "cyan",
  onClose,
}: ShellTextPanelProps): React.ReactNode {
  const scrollRef = useRef<ScrollBoxHandle | null>(null);
  const [atBottom, setAtBottom] = useState(false);

  const syncBottomState = useCallback(() => {
    const handle = scrollRef.current;
    if (!handle) return;
    const maxTop = Math.max(0, handle.getScrollHeight() - handle.getViewportHeight());
    const remaining = maxTop - handle.getScrollTop();
    setAtBottom(remaining <= 2);
  }, []);

  const scrollByPage = useCallback((dir: -1 | 1) => {
    const handle = scrollRef.current;
    if (!handle) return;
    const amount = Math.max(1, Math.floor((handle.getViewportHeight() || 20) * 0.85));
    handle.scrollBy(dir * amount);
    setTimeout(syncBottomState, 0);
  }, [syncBottomState]);

  const scrollToEdge = useCallback((edge: "top" | "bottom") => {
    const handle = scrollRef.current;
    if (!handle) return;
    if (edge === "top") {
      handle.scrollTo(0);
      setAtBottom(false);
      return;
    }
    handle.scrollToBottom();
    setAtBottom(true);
  }, []);

  useInput((_input: string, key: Key) => {
    if (key.escape) {
      onClose();
      return;
    }
    if (key.pageUp || key.upArrow) {
      scrollByPage(-1);
      return;
    }
    if (key.pageDown || key.downArrow) {
      scrollByPage(1);
      return;
    }
    if (key.home || (key.ctrl && key.home)) {
      scrollToEdge("top");
      return;
    }
    if (key.end || (key.ctrl && key.end)) {
      scrollToEdge("bottom");
    }
  });

  const footer = useMemo(
    () =>
      atBottom
        ? "PgUp/PgDn to scroll · Esc to close"
        : "PgUp/PgDn to scroll · End to jump to bottom · Esc to close",
    [atBottom],
  );

  return (
    <Box flexDirection="column" paddingX={1} borderStyle="round" borderColor={accentColor}>
      <Box marginBottom={subtitle ? 0 : 1}>
        <Text bold color={accentColor}>{`  ${title}`}</Text>
      </Box>
      {subtitle ? (
        <Box marginBottom={1}>
          <Text dimColor>{subtitle}</Text>
        </Box>
      ) : null}
      <ScrollBox ref={scrollRef} flexDirection="column" flexGrow={0} height={20}>
        {lines.map((line, index) => (
          <Text key={`${index}:${line}`}>{line}</Text>
        ))}
      </ScrollBox>
      <Box marginTop={1}>
        <Text dimColor>{footer}</Text>
      </Box>
    </Box>
  );
}
