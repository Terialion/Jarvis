import { Box, Text, type Key, useInput } from "../ink-renderer/index.js";
import type React from "react";
import { useCallback, useRef, useState } from "react";

export type HelpCommandEntry = {
  name: string;
  description: string;
  aliases?: string[];
};

export type HelpPopupProps = {
  commands: HelpCommandEntry[];
  onClose: () => void;
};

export function HelpPopup({ commands, onClose }: HelpPopupProps): React.ReactNode {
  const [focusedIndex, setFocusedIndex] = useState(0);
  const focusedIndexRef = useRef(0);

  const clamp = useCallback((value: number, min: number, max: number) => {
    return Math.min(max, Math.max(min, value));
  }, []);

  const moveFocus = useCallback((delta: 1 | -1) => {
    focusedIndexRef.current = clamp(
      focusedIndexRef.current + delta,
      0,
      commands.length - 1,
    );
    setFocusedIndex(focusedIndexRef.current);
  }, [clamp, commands.length]);

  useInput((_input: string, key: Key) => {
    if (key.escape) {
      onClose();
      return;
    }
    if (key.upArrow) {
      moveFocus(-1);
      return;
    }
    if (key.downArrow) {
      moveFocus(1);
    }
  });

  return (
    <Box flexDirection="column" paddingX={1} borderStyle="round" borderColor="cyan">
      <Box marginBottom={1}>
        <Text bold color="cyan">  Help</Text>
      </Box>
      <Box flexDirection="column">
        {commands.map((cmd, index) => {
          const focused = index === focusedIndex;
          const aliases = cmd.aliases?.length ? ` (${cmd.aliases.join(", ")})` : "";
          return (
            <Box key={cmd.name}>
              <Text color={focused ? "cyan" : undefined} bold={focused}>
                {focused ? "❯ " : "  "}
              </Text>
              <Text color={focused ? "cyan" : undefined} bold={focused}>
                /{cmd.name}{aliases}
              </Text>
              <Text dimColor>{` — ${cmd.description}`}</Text>
            </Box>
          );
        })}
      </Box>
      <Box marginTop={1}>
        <Text dimColor>↑↓ to navigate · Esc to close</Text>
      </Box>
    </Box>
  );
}
