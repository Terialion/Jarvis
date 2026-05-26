// ============================================================================
// HistoryPager — full-screen conversation history overlay (Codex Ctrl+T pattern)
// ============================================================================

import { Box, Text, useInput } from "../ink-renderer/index.js";
import type React from "react";
import { useState, useCallback } from "react";

export type HistoryPagerProps = {
  messageCount: number;
  /** Called when user requests exit (q/Esc) */
  onExit: () => void;
  children?: React.ReactNode;
};

export function HistoryPager({ messageCount, onExit, children }: HistoryPagerProps): React.ReactNode {
  const [scrollHint, setScrollHint] = useState('');
  useInput(
    useCallback((input: string, key: { upArrow?: boolean; downArrow?: boolean; escape?: boolean; return?: boolean }) => {
      if (key.escape || input === 'q') {
        onExit();
        return;
      }
      if (input === 'j') { setScrollHint('↓ scroll down'); return; }
      if (input === 'k') { setScrollHint('↑ scroll up'); return; }
      if (input === 'g') { setScrollHint('↖ top'); return; }
      if (input === 'G') { setScrollHint('↘ bottom'); return; }
    }, [onExit]),
  );

  return (
    <Box flexDirection="column" flexGrow={1} paddingX={1}>
      {/* Header */}
      <Box flexDirection="row" justifyContent="space-between">
        <Text bold> History ({messageCount} messages)</Text>
        <Text dimColor>j/k ↑↓ scroll · g/G top/bottom · q/Esc exit</Text>
      </Box>
      <Box>
        <Text dimColor>{"─".repeat(process.stdout.columns ? Math.min(process.stdout.columns - 2, 78) : 78)}</Text>
      </Box>
      {/* Scroll hint */}
      {scrollHint && (
        <Box>
          <Text color="#DA7756">{scrollHint}</Text>
        </Box>
      )}
      {/* Message content */}
      <Box flexDirection="column" flexGrow={1}>
        {children}
      </Box>
    </Box>
  );
}
