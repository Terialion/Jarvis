/**
 * PromptInput — fixed bottom input bar with slash-completion, history, and
 * smart Enter key (submit at end, newline mid-input).
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
  placeholder = "Ask Jarvis... (Enter=submit, Alt+Enter=newline)",
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
    <Box
      height={3}
      flexShrink={0}
      borderStyle="round"
      borderColor={isStreaming ? "yellow" : "green"}
      paddingLeft={1}
    >
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
