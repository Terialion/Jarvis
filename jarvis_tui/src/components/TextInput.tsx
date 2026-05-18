/**
 * TextInput — minimal replacement for ink-text-input that filters all
 * Ctrl-modified keys so shortcuts (Ctrl+T, Ctrl+O, etc.) don't leak into
 * the input field.
 */
import React, { useState, useEffect } from "react";
import { Text, useInput } from "ink";

interface TextInputProps {
  value: string;
  placeholder?: string;
  focus?: boolean;
  showCursor?: boolean;
  onChange: (value: string) => void;
  onSubmit?: (value: string) => void;
}

export const TextInput: React.FC<TextInputProps> = ({
  value: originalValue,
  placeholder = "",
  focus = true,
  showCursor = true,
  onChange,
  onSubmit,
}) => {
  const [{ cursorOffset }, setState] = useState({
    cursorOffset: (originalValue || "").length,
  });

  useEffect(() => {
    setState((prev) => {
      if (!focus || !showCursor) return prev;
      const newValue = originalValue || "";
      if (prev.cursorOffset > newValue.length - 1) {
        return { cursorOffset: newValue.length };
      }
      return prev;
    });
  }, [originalValue, focus, showCursor]);

  useInput(
    (input, key) => {
      // Filter ALL Ctrl-modified keys — prevents shortcut leakage
      if (key.ctrl) return;
      if (key.meta) return;
      if (key.tab) return;

      if (key.return) {
        onSubmit?.(originalValue);
        return;
      }
      if (key.upArrow || key.downArrow) return;

      let nextCursorOffset = cursorOffset;
      let nextValue = originalValue;

      if (key.leftArrow) {
        nextCursorOffset = Math.max(0, cursorOffset - 1);
      } else if (key.rightArrow) {
        nextCursorOffset = Math.min(originalValue.length, cursorOffset + 1);
      } else if (key.backspace || key.delete) {
        if (cursorOffset > 0) {
          nextValue =
            originalValue.slice(0, cursorOffset - 1) +
            originalValue.slice(cursorOffset);
          nextCursorOffset--;
        }
      } else if (input) {
        nextValue =
          originalValue.slice(0, cursorOffset) +
          input +
          originalValue.slice(cursorOffset);
        nextCursorOffset += input.length;
      } else {
        return;
      }

      setState({ cursorOffset: nextCursorOffset });

      if (nextValue !== originalValue) {
        onChange(nextValue);
      }
    },
    { isActive: focus },
  );

  // Render with cursor indicator
  const value = originalValue;
  let rendered: string;

  if (showCursor && focus) {
    if (value.length === 0) {
      rendered = "\x1b[7m \x1b[27m"; // inverse space as cursor
      if (placeholder) {
        rendered += `\x1b[2m${placeholder}\x1b[22m`;
      }
    } else {
      rendered = "";
      for (let i = 0; i < value.length; i++) {
        if (i === cursorOffset && cursorOffset < value.length) {
          rendered += `\x1b[7m${value[i]}\x1b[27m`;
        } else {
          rendered += value[i];
        }
      }
      if (cursorOffset === value.length) {
        rendered += "\x1b[7m \x1b[27m";
      }
    }
  } else if (value.length === 0 && placeholder) {
    rendered = `\x1b[2m${placeholder}\x1b[22m`;
  } else {
    rendered = value;
  }

  return <Text>{rendered}</Text>;
};
