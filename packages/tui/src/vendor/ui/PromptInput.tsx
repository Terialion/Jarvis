import { Box, type Key, Text, useInput } from "../ink-renderer/index.js";
import type React from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  lineOffset as computeLineOffset,
  cursorLineIndex,
  filterCommands,
  wordBwd,
  wordFwd,
} from "./utils/promptInputLogic";
import type { FileEntry } from "./utils/fileScanner";

type Command = { name: string; description: string };
type VimMode = "NORMAL" | "INSERT";

type PromptInputProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (value: string) => void;
  allowEmptySubmit?: boolean;
  placeholder?: string;
  prefix?: string;
  prefixColor?: string;
  disabled?: boolean;
  /** When true, Esc is not consumed so parent can handle interrupt */
  isLoading?: boolean;
  commands?: Command[];
  onCommandSelect?: (name: string) => void;
  history?: string[];
  vimMode?: boolean;
  multiline?: boolean;
  /** File entries for @ file reference */
  fileEntries?: FileEntry[];
  /** Called when @ is triggered or query changes — parent should call scanFiles */
  onFileSearch?: (query: string) => void;
};

const MAX_VISIBLE_FILE_ENTRIES = 15;

export function PromptInput({
  value,
  onChange,
  onSubmit,
  allowEmptySubmit = false,
  placeholder = "",
  prefix = "❯",
  prefixColor = "cyan",
  disabled = false,
  isLoading = false,
  commands = [],
  onCommandSelect,
  history = [],
  vimMode = false,
  multiline = false,
  fileEntries = [],
  onFileSearch,
}: PromptInputProps): React.ReactNode {
  const [cursor, setCursor] = useState(0);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const [suggestionIndex, setSuggestionIndex] = useState(0);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [selectedCommand, setSelectedCommand] = useState<string | null>(null);
  const suppressSuggestionsRef = useRef(false);
  const MAX_VISIBLE_SUGGESTIONS = 8;
  const [vim, setVim] = useState<VimMode>("INSERT");
  const [pendingD, setPendingD] = useState(false);
  const isVimNormal = vimMode && vim === "NORMAL";

  // @ file reference state
  const [showFilePicker, setShowFilePicker] = useState(false);
  const [filePickerIndex, setFilePickerIndex] = useState(0);
  const [atPosition, setAtPosition] = useState(-1); // position of @ in input

  const suggestions = commands.length > 0 ? filterCommands(commands, value) : [];
  const hasSuggestions = showSuggestions && suggestions.length > 0;

  // Compute @ file reference state
  const atQuery = atPosition >= 0 ? value.slice(atPosition + 1, cursor) : "";
  const hasFilePicker = showFilePicker && atPosition >= 0;

  const lines = multiline ? value.split("\n") : [value];
  const cursorLine = multiline ? cursorLineIndex(lines, cursor) : 0;

  const lineOffset = (line: number): number => computeLineOffset(lines, line);

  useEffect(() => {
    setCursor((prev) => Math.min(prev, value.length));
    if (suppressSuggestionsRef.current) {
      suppressSuggestionsRef.current = false;
      return;
    }
    setShowSuggestions(value.startsWith("/"));
    setSelectedCommand(null);
    setSuggestionIndex((prev) => {
      if (!value.startsWith("/")) return 0;
      return suggestions.length === 0 ? 0 : Math.min(prev, suggestions.length - 1);
    });

    // Detect @ file reference: find the last @ before cursor that's not inside a word
    const textBeforeCursor = value.slice(0, cursor);
    const lastAtIndex = textBeforeCursor.lastIndexOf("@");
    if (lastAtIndex >= 0) {
      // @ should be at start or preceded by whitespace
      const charBefore = lastAtIndex > 0 ? textBeforeCursor[lastAtIndex - 1] : " ";
      if (lastAtIndex === 0 || charBefore === " " || charBefore === "\n") {
        const query = textBeforeCursor.slice(lastAtIndex + 1);
        // Don't trigger if there's a space right after @ with no query
        if (!query.includes(" ") || query.trim().length > 0) {
          setAtPosition(lastAtIndex);
          setShowFilePicker(true);
          setFilePickerIndex(0);
          onFileSearch?.(query);
          return;
        }
      }
    }
    setShowFilePicker(false);
    setAtPosition(-1);
  }, [suggestions.length, value, cursor, onFileSearch]);

  const updateValue = useCallback(
    (nv: string, nc?: number) => {
      onChange(nv);
      setCursor(nc ?? nv.length);
      setHistoryIndex(-1);
      setShowSuggestions(nv.startsWith("/"));
      setSuggestionIndex(0);
      setSelectedCommand(null);
      // Note: file picker state is managed by useEffect based on @ detection
    },
    [onChange],
  );

  const insertNewline = () => {
    updateValue(`${value.slice(0, cursor)}\n${value.slice(cursor)}`, cursor + 1);
  };

  const moveLine = (dir: -1 | 1) => {
    const target = cursorLine + dir;
    if (multiline && target >= 0 && target < lines.length) {
      const col = cursor - lineOffset(cursorLine);
      setCursor(lineOffset(target) + Math.min(col, lines[target]!.length));
      return true;
    }
    return false;
  };

  const historyUp = () => {
    if (history.length > 0 && historyIndex + 1 < history.length) {
      const ni = historyIndex + 1;
      setHistoryIndex(ni);
      const hv = history[ni]!;
      suppressSuggestionsRef.current = true;
      onChange(hv);
      setCursor(hv.length);
    }
  };
  const historyDown = () => {
    if (historyIndex > 0) {
      const ni = historyIndex - 1;
      setHistoryIndex(ni);
      const hv = history[ni]!;
      suppressSuggestionsRef.current = true;
      onChange(hv);
      setCursor(hv.length);
    } else if (historyIndex === 0) {
      setHistoryIndex(-1);
      onChange("");
      setCursor(0);
    }
  };

  // Filter file entries based on @ query
  const filteredFileEntries = hasFilePicker
    ? fileEntries.filter((entry) => {
        const q = atQuery.toLowerCase();
        if (!q) return true;
        return (
          entry.path.toLowerCase().includes(q) ||
          entry.path.split("/").pop()!.toLowerCase().includes(q)
        );
      })
    : [];

  useInput(
    (input: string, key: Key) => {
      if (disabled) return;

      if (isVimNormal) {
        if (input !== "d") setPendingD(false);

        if (input === "i") {
          setVim("INSERT");
          return;
        }
        if (input === "a") {
          setVim("INSERT");
          setCursor((c) => Math.min(value.length, c + 1));
          return;
        }
        if (input === "h" || key.leftArrow) {
          setCursor((c) => Math.max(0, c - 1));
          return;
        }
        if (input === "l" || key.rightArrow) {
          setCursor((c) => Math.min(Math.max(0, value.length - 1), c + 1));
          return;
        }
        if (input === "0" || key.home) {
          setCursor(multiline ? lineOffset(cursorLine) : 0);
          return;
        }
        if (input === "$" || key.end) {
          if (multiline) {
            const endOfLine = lineOffset(cursorLine) + lines[cursorLine]!.length;
            setCursor(Math.max(lineOffset(cursorLine), endOfLine - 1));
          } else {
            setCursor(Math.max(0, value.length - 1));
          }
          return;
        }
        if (input === "w") {
          setCursor(wordFwd(value, cursor));
          return;
        }
        if (input === "b") {
          setCursor(wordBwd(value, cursor));
          return;
        }
        if (input === "x") {
          if (cursor < value.length) {
            const nv = value.slice(0, cursor) + value.slice(cursor + 1);
            updateValue(nv, Math.min(cursor, Math.max(0, nv.length - 1)));
          }
          return;
        }
        if (input === "d") {
          if (!pendingD) {
            setPendingD(true);
            return;
          }
          setPendingD(false);
          if (multiline && lines.length > 1) {
            const pos = lineOffset(cursorLine);
            const end = pos + lines[cursorLine]!.length;
            const from = cursorLine === 0 ? pos : pos - 1;
            const to = cursorLine === 0 ? Math.min(end + 1, value.length) : end;
            const nv = value.slice(0, from) + value.slice(to);
            updateValue(nv, Math.min(from, Math.max(0, nv.length - 1)));
          } else {
            updateValue("", 0);
          }
          return;
        }
        if (key.upArrow || (input === "k" && !key.ctrl)) {
          if (!moveLine(-1)) historyUp();
          return;
        }
        if (key.downArrow || (input === "j" && !key.ctrl)) {
          if (!moveLine(1)) historyDown();
          return;
        }
        if (key.return && value.length > 0) {
          onSubmit(value);
          return;
        }
        return;
      }

      if (key.return) {
        if (hasSuggestions) {
          const name = selectedCommand ?? suggestions[suggestionIndex]?.name;
          if (name) {
            const cv = `/${name}`;
            onCommandSelect?.(name);
            suppressSuggestionsRef.current = true;
            onChange(cv);
            setCursor(cv.length);
            setShowSuggestions(false);
            setSuggestionIndex(0);
            setSelectedCommand(null);
          }
          return;
        }
        // File picker: insert selected file path
        if (hasFilePicker && filteredFileEntries.length > 0) {
          const entry = filteredFileEntries[filePickerIndex];
          if (entry) {
            const beforeAt = value.slice(0, atPosition);
            const afterCursor = value.slice(cursor);
            const newValue = `${beforeAt}@${entry.path} ${afterCursor}`;
            onChange(newValue);
            setCursor(atPosition + 1 + entry.path.length + 1);
            setShowFilePicker(false);
            setAtPosition(-1);
          }
          return;
        }
        if (multiline && key.shift) {
          insertNewline();
          return;
        }
        if (value.length > 0 || allowEmptySubmit) onSubmit(value);
        return;
      }
      if (key.escape) {
        // Let parent handle Esc when loading (for interrupt)
        if (isLoading) return;
        if (hasSuggestions) {
          setShowSuggestions(false);
          return;
        }
        if (hasFilePicker) {
          setShowFilePicker(false);
          setAtPosition(-1);
          return;
        }
        if (vimMode) {
          setVim("NORMAL");
          return;
        }
        return;
      }
      if (multiline && key.ctrl && input === "j") {
        insertNewline();
        return;
      }
      if (key.tab) {
        if (hasSuggestions) {
          updateValue(`/${suggestions[suggestionIndex]!.name} `);
          return;
        }
        if (hasFilePicker && filteredFileEntries.length > 0) {
          const entry = filteredFileEntries[filePickerIndex];
          if (entry) {
            const beforeAt = value.slice(0, atPosition);
            const afterCursor = value.slice(cursor);
            const newValue = `${beforeAt}@${entry.path} ${afterCursor}`;
            onChange(newValue);
            setCursor(atPosition + 1 + entry.path.length + 1);
            setShowFilePicker(false);
            setAtPosition(-1);
          }
          return;
        }
        return;
      }
      if (key.upArrow) {
        if (hasSuggestions) {
          setSuggestionIndex((i) => {
            const next = i > 0 ? i - 1 : suggestions.length - 1;
            setSelectedCommand(suggestions[next]?.name ?? null);
            return next;
          });
          return;
        }
        if (hasFilePicker) {
          setFilePickerIndex((i) => (i > 0 ? i - 1 : filteredFileEntries.length - 1));
          return;
        }
        if (!moveLine(-1)) historyUp();
        return;
      }
      if (key.downArrow) {
        if (hasSuggestions) {
          setSuggestionIndex((i) => {
            const next = i < suggestions.length - 1 ? i + 1 : 0;
            setSelectedCommand(suggestions[next]?.name ?? null);
            return next;
          });
          return;
        }
        if (hasFilePicker) {
          setFilePickerIndex((i) => (i < filteredFileEntries.length - 1 ? i + 1 : 0));
          return;
        }
        if (!moveLine(1)) historyDown();
        return;
      }
      if (key.leftArrow) {
        setCursor((c) => Math.max(0, c - 1));
        return;
      }
      if (key.rightArrow) {
        setCursor((c) => Math.min(value.length, c + 1));
        return;
      }
      if (key.home || (key.ctrl && input === "a")) {
        setCursor(0);
        return;
      }
      if (key.end || (key.ctrl && input === "e")) {
        setCursor(value.length);
        return;
      }
      if (key.ctrl && input === "w") {
        if (cursor > 0) {
          let i = cursor - 1;
          while (i > 0 && value[i - 1] === " ") i--;
          while (i > 0 && value[i - 1] !== " ") i--;
          updateValue(value.slice(0, i) + value.slice(cursor), i);
        }
        return;
      }
      if (key.ctrl && input === "u") {
        updateValue(value.slice(cursor), 0);
        return;
      }
      if (key.backspace || input === "\b" || input === "\u007f") {
        if (cursor > 0) updateValue(value.slice(0, cursor - 1) + value.slice(cursor), cursor - 1);
        return;
      }
      if (key.delete) {
        if (cursor < value.length)
          updateValue(value.slice(0, cursor) + value.slice(cursor + 1), cursor);
        return;
      }
      if (key.ctrl || key.meta) return;
      if (input.length > 0)
        updateValue(value.slice(0, cursor) + input + value.slice(cursor), cursor + input.length);
    },
    { isActive: !disabled },
  );

  const renderCursor = (text: string, cur: number): React.ReactNode => {
    if (text.length === 0 && placeholder && cursor === 0) {
      return (
        <Text>
          <Text inverse> </Text>
          <Text dimColor>{placeholder}</Text>
        </Text>
      );
    }
    const before = text.slice(0, cur);
    const at = cur < text.length ? text[cur]! : " ";
    const after = cur < text.length ? text.slice(cur + 1) : "";
    return (
      <Text>
        {before}
        <Text inverse>{at}</Text>
        {after}
      </Text>
    );
  };

  const vimTag = vimMode ? <Text dimColor>{` -- ${vim} --`}</Text> : null;

  const renderContent = (): React.ReactNode => {
    if (!multiline || lines.length <= 1) {
      return (
        <Box>
          <Text color={prefixColor}>{prefix} </Text>
          {renderCursor(value, cursor)}
          {vimTag}
        </Box>
      );
    }
    let off = 0;
    return (
      <Box flexDirection="column">
        {lines.map((line, i) => {
          const ls = off;
          off += line.length + 1;
          const active = i === cursorLine;
          return (
            <Box key={ls}>
              <Text color={prefixColor}>{i === 0 ? `${prefix} ` : "∙ "}</Text>
              {active ? renderCursor(line, cursor - ls) : <Text>{line}</Text>}
              {i === lines.length - 1 && vimTag}
            </Box>
          );
        })}
      </Box>
    );
  };

  return (
    <Box flexDirection="column">
      {renderContent()}
      {hasSuggestions && (() => {
        const total = suggestions.length;
        const max = MAX_VISIBLE_SUGGESTIONS;
        // Scroll offset: keep selected item centered
        let scrollOffset = 0;
        if (total > max) {
          const half = Math.floor(max / 2);
          if (suggestionIndex <= half) scrollOffset = 0;
          else if (suggestionIndex >= total - max + half) scrollOffset = total - max;
          else scrollOffset = suggestionIndex - half;
        }
        const visible = suggestions.slice(scrollOffset, scrollOffset + max);
        const hasAbove = scrollOffset > 0;
        const hasBelow = scrollOffset + max < total;

        return (
          <Box flexDirection="column" marginLeft={2}>
            {hasAbove && (
              <Text dimColor>{`  ↑ ${scrollOffset} more`}</Text>
            )}
            {visible.map((cmd, vi) => {
              const i = scrollOffset + vi;
              const isFocused = i === suggestionIndex;
              return (
                <Box key={cmd.name}>
                  <Text color={isFocused ? "cyan" : undefined}>{isFocused ? "❯" : " "} </Text>
                  <Text color={isFocused ? "cyan" : undefined} bold={isFocused}>
                    {`/${cmd.name}`}
                  </Text>
                  <Text dimColor>{`  ${cmd.description.slice(0, 80)}`}</Text>
                </Box>
              );
            })}
            {hasBelow && (
              <Text dimColor>{`  ↓ ${total - scrollOffset - max} more`}</Text>
            )}
          </Box>
        );
      })()}
      {hasFilePicker && filteredFileEntries.length > 0 && (() => {
        const total = filteredFileEntries.length;
        const max = MAX_VISIBLE_FILE_ENTRIES;
        let scrollOffset = 0;
        if (total > max) {
          const half = Math.floor(max / 2);
          if (filePickerIndex <= half) scrollOffset = 0;
          else if (filePickerIndex >= total - max + half) scrollOffset = total - max;
          else scrollOffset = filePickerIndex - half;
        }
        const visible = filteredFileEntries.slice(scrollOffset, scrollOffset + max);
        const hasAbove = scrollOffset > 0;
        const hasBelow = scrollOffset + max < total;

        return (
          <Box flexDirection="column" marginLeft={2}>
            <Text dimColor>  Files matching "@{atQuery}":</Text>
            {hasAbove && (
              <Text dimColor>{`  ↑ ${scrollOffset} more`}</Text>
            )}
            {visible.map((entry, vi) => {
              const i = scrollOffset + vi;
              const isFocused = i === filePickerIndex;
              const icon = entry.isDir ? "📁 " : "📄 ";
              return (
                <Box key={entry.path}>
                  <Text color={isFocused ? "cyan" : undefined}>{isFocused ? "❯" : " "}</Text>
                  <Text color={isFocused ? "cyan" : undefined} bold={isFocused}>
                    {`${icon}${entry.path}`}
                  </Text>
                </Box>
              );
            })}
            {hasBelow && (
              <Text dimColor>{`  ↓ ${total - scrollOffset - max} more`}</Text>
            )}
          </Box>
        );
      })()}
    </Box>
  );
}
