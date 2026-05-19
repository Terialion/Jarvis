/**
 * PromptInput — Claude Code / Codex style input line.
 *
 * Format:
 *   ❯ input text here
 *
 * No border, no nested box — clean single-line input with ❯ prefix.
 * Placeholder follows Codex's "Ask Codex to do anything" pattern.
 */
import React, { useState, useCallback } from "react";
import { Box, Text } from "ink";
import { TextInput } from "./TextInput.js";

interface PromptInputProps {
  onSubmit: (text: string) => void;
  isStreaming: boolean;
  placeholder?: string;
}

export const PromptInput: React.FC<PromptInputProps> = ({
  onSubmit,
  isStreaming,
  placeholder = "Ask Jarvis...",
}) => {
  const [value, setValue] = useState("");

  const handleSubmit = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (trimmed && !isStreaming) {
        onSubmit(trimmed);
        setValue("");
      }
    },
    [onSubmit, isStreaming],
  );

  return (
    <Box height={1} flexShrink={0}>
      <Text bold color="cyan">
        ❯{" "}
      </Text>
      <TextInput
        value={value}
        onChange={setValue}
        onSubmit={handleSubmit}
        placeholder={placeholder}
      />
    </Box>
  );
};
