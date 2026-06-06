import { Box, TerminalSizeContext, Text, useInput } from "../ink-renderer/index.js";
import React, { useCallback, useContext, useMemo } from "react";
import { getStableLineEntries } from "./utils/stableKeys";

export type PermissionAction = "allow" | "always_allow" | "deny";

export type PermissionRequestProps = {
  toolName: string;
  description: string;
  /** Optional details (command, file path, diff, etc.) */
  details?: string;
  /** Specific pattern label for "always allow" (e.g., file path or command) */
  patternLabel?: string;
  /** Whether to show "Always Allow" option (default true) */
  showAlwaysAllow?: boolean;
  /** Callback when user makes a decision */
  onDecision: (action: PermissionAction, feedback?: string) => void;
  /** Optional custom content between description and buttons */
  children?: React.ReactNode;
  /** Optional: render a DiffView or code preview */
  preview?: React.ReactNode;
};

export function BashPermissionContent({ command }: { command: string }): React.ReactNode {
  return (
    <Box flexDirection="column">
      <Text>Run command:</Text>
      <Box marginLeft={2}>
        <Text color="yellow">{command}</Text>
      </Box>
    </Box>
  );
}

export function FileEditPermissionContent({
  filename,
  diff,
}: {
  filename: string;
  diff: string;
}): React.ReactNode {
  const diffLines = getStableLineEntries(diff, `permission:${filename}`);

  return (
    <Box flexDirection="column">
      <Text>
        Edit file:{" "}
        <Text color="cyan" bold>
          {filename}
        </Text>
      </Text>
      {diff && (
        <Box marginTop={1} flexDirection="column">
          {diffLines.map(({ key, line }) => {
            let color: string | undefined;
            if (line.startsWith("+")) color = "green";
            else if (line.startsWith("-")) color = "red";
            else if (line.startsWith("@")) color = "cyan";
            return (
              <Text key={key} color={color} dimColor={!color && !line.startsWith("+")}>
                {line}
              </Text>
            );
          })}
        </Box>
      )}
    </Box>
  );
}

type OptionDef = {
  value: PermissionAction;
  label: string;
  key: string;
};

export function PermissionRequest({
  toolName,
  description,
  details,
  patternLabel,
  showAlwaysAllow = true,
  onDecision,
  children,
  preview,
}: PermissionRequestProps): React.ReactNode {
  const terminalSize = useContext(TerminalSizeContext);
  const terminalWidth = Math.min((terminalSize?.columns ?? 80) - 2, 80);

  const options = useMemo<OptionDef[]>(() => {
    const opts: OptionDef[] = [{ value: "allow", label: "Yes, allow", key: "y" }];
    if (showAlwaysAllow) {
      const truncated = patternLabel && patternLabel.length > 40
        ? patternLabel.slice(0, 37) + '...'
        : patternLabel;
      const target = truncated ? `${toolName} (${truncated})` : toolName;
      opts.push({ value: "always_allow", label: `Always allow ${target}`, key: "a" });
    }
    opts.push({ value: "deny", label: "No, deny", key: "n" });
    return opts;
  }, [showAlwaysAllow, toolName, patternLabel]);

  const [focusIndex, setFocusIndex] = React.useState(0);
  const focusRef = React.useRef(focusIndex);
  focusRef.current = focusIndex;

  const decide = useCallback(
    (action: PermissionAction) => {
      onDecision(action);
    },
    [onDecision],
  );

  useInput((input, key) => {
    if (input === "y") {
      decide("allow");
      return;
    }
    if (input === "a" && showAlwaysAllow) {
      decide("always_allow");
      return;
    }
    if (input === "n" || key.escape) {
      decide("deny");
      return;
    }

    if (key.upArrow || input === "k") {
      setFocusIndex((prev) => (prev - 1 + options.length) % options.length);
    } else if (key.downArrow || input === "j") {
      setFocusIndex((prev) => (prev + 1) % options.length);
    } else if (key.return) {
      decide(options[focusRef.current]!.value);
    } else if (input >= "1" && input <= "9") {
      const idx = parseInt(input, 10) - 1;
      if (idx < options.length) {
        setFocusIndex(idx);
        decide(options[idx]!.value);
      }
    }
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Compact header: tool name + description on one line */}
      <Box>
        <Text bold color="cyan">{toolName}</Text>
        <Text dimColor> — </Text>
        <Text>{description}</Text>
      </Box>

      {/* Details (command, file path) */}
      {details && (
        <Box marginLeft={2} marginTop={0}>
          <Text color="yellow">{details}</Text>
        </Box>
      )}

      {/* Diff preview */}
      {children && (
        <Box marginLeft={2} marginTop={0} flexDirection="column">
          {children}
        </Box>
      )}

      {preview && (
        <Box marginLeft={2} marginTop={0} flexDirection="column">
          {preview}
        </Box>
      )}

      {/* Options: vertical list with key shortcuts */}
      <Box marginTop={1} flexDirection="column">
        {options.map((opt, i) => {
          const isFocused = i === focusIndex;
          return (
            <Box key={opt.value}>
              <Text color={isFocused ? "cyan" : undefined}>{isFocused ? "❯" : " "}</Text>
              <Text color={isFocused ? "cyan" : undefined} bold={isFocused}>
                {opt.key}
              </Text>
              <Text dimColor>{") "}</Text>
              <Text color={isFocused ? "cyan" : undefined}>
                {opt.label}
              </Text>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
