import { Box, Text, type Key, useInput } from "../ink-renderer/index.js";
import type React from "react";
import { useCallback, useRef, useState } from "react";
import { parseModelName, type ModelInfo } from "@jarvis/agent";

// ============================================================================
// Types
// ============================================================================

export type ModelSelectionResult = {
  /** Clean model slug */
  model: string;
  /** "default" = persist to settings, "session" = this session only */
  mode: "default" | "session";
};

export type ModelSelectorProps = {
  /** Currently active model (with optional [size] annotation) */
  currentModel: string;
  /** Current reasoning effort */
  currentEffort: string;
  /** All known models from the catalog */
  knownModels: ModelInfo[];
  /** Called when user confirms selection */
  onSelect: (result: ModelSelectionResult) => void;
  /** Called when user cancels */
  onCancel: () => void;
  /** Called when effort changes */
  onEffortChange?: (effort: string) => void;
};

// ============================================================================
// Model entry for display
// ============================================================================

interface ModelDisplayEntry {
  slug: string;
  displayName: string;
  provider: string;
  contextWindow: number;
  maxContextWindow: number;
  isCurrent: boolean;
  isCustom: boolean;
}

// ============================================================================
// Effort levels
// ============================================================================

const EFFORT_LEVELS = ["high", "medium", "low"] as const;

const EFFORT_LABELS: Record<string, string> = {
  high: "High effort (default)",
  medium: "Medium effort",
  low: "Low effort",
};

function formatContextWindow(tokens: number): string {
  if (tokens >= 1_000_000) {
    const m = tokens / 1_000_000;
    return `${m === Math.round(m) ? Math.round(m) : m.toFixed(1)}M context`;
  }
  const k = tokens / 1_000;
  return `${Math.round(k)}K context`;
}

function providerLabel(provider: string): string {
  switch (provider) {
    case "deepseek": return "DeepSeek";
    case "qwen": return "Qwen";
    case "openai": return "OpenAI";
    case "anthropic": return "Anthropic";
    case "google": return "Google";
    case "openrouter": return "OpenRouter";
    default: return provider;
  }
}

// ============================================================================
// Component
// ============================================================================

export function ModelSelector({
  currentModel,
  currentEffort,
  knownModels,
  onSelect,
  onCancel,
  onEffortChange,
}: ModelSelectorProps): React.ReactNode {
  const parsed = parseModelName(currentModel);
  const currentSlug = parsed.cleanName;
  const [effortIndex, setEffortIndex] = useState(
    Math.max(0, EFFORT_LEVELS.indexOf(currentEffort as typeof EFFORT_LEVELS[number])),
  );
  const selectCalledRef = useRef(false);

  // Build display entries: known models + current custom model
  const entries: ModelDisplayEntry[] = knownModels.map((m) => ({
    slug: m.slug,
    displayName: m.displayName,
    provider: m.provider,
    contextWindow: m.contextWindow,
    maxContextWindow: m.maxContextWindow,
    isCurrent: m.slug === currentSlug,
    isCustom: false,
  }));

  // Add current model as custom if not in catalog
  const isCustom = !knownModels.some((m) => m.slug === currentSlug);
  if (isCustom && currentSlug) {
    entries.push({
      slug: currentSlug,
      displayName: currentSlug,
      provider: "",
      contextWindow: parsed.contextWindow ?? 128_000,
      maxContextWindow: parsed.contextWindow ?? 128_000,
      isCurrent: true,
      isCustom: true,
    });
  }

  // Find the current model entry index for initial focus
  const currentEntryIndex = entries.findIndex((e) => e.isCurrent);
  const initialFocusIndex = currentEntryIndex >= 0 ? currentEntryIndex : 0;

  const [focusedIndex, setFocusedIndex] = useState(initialFocusIndex);
  const focusedIndexRef = useRef(initialFocusIndex);
  const effortIndexRef = useRef(effortIndex);

  const clamp = useCallback((value: number, min: number, max: number) => {
    return Math.min(max, Math.max(min, value));
  }, []);

  const moveFocus = useCallback((delta: 1 | -1) => {
    focusedIndexRef.current = clamp(
      focusedIndexRef.current + delta,
      0,
      entries.length - 1,
    );
    setFocusedIndex(focusedIndexRef.current);
  }, [clamp, entries.length]);

  const changeEffort = useCallback((delta: 1 | -1) => {
    effortIndexRef.current = clamp(
      effortIndexRef.current + delta,
      0,
      EFFORT_LEVELS.length - 1,
    );
    setEffortIndex(effortIndexRef.current);
    onEffortChange?.(EFFORT_LEVELS[effortIndexRef.current]!);
  }, [clamp, onEffortChange]);

  useInput((_input: string, key: Key) => {
    if (selectCalledRef.current) return;

    if (key.escape) {
      selectCalledRef.current = true;
      onCancel();
      return;
    }

    if (key.return) {
      selectCalledRef.current = true;
      const entry = entries[focusedIndexRef.current];
      if (entry) {
        onSelect({ model: entry.slug, mode: "default" });
      }
      return;
    }

    if (_input === "s" && !key.ctrl && !key.meta) {
      selectCalledRef.current = true;
      const entry = entries[focusedIndexRef.current];
      if (entry) {
        onSelect({ model: entry.slug, mode: "session" });
      }
      return;
    }

    if (key.upArrow || (_input === "k" && !key.ctrl && !key.meta)) {
      moveFocus(-1);
      return;
    }
    if (key.downArrow || (_input === "j" && !key.ctrl && !key.meta)) {
      moveFocus(1);
      return;
    }
    if (key.leftArrow || (_input === "h" && !key.ctrl && !key.meta)) {
      changeEffort(-1);
      return;
    }
    if (key.rightArrow || (_input === "l" && !key.ctrl && !key.meta)) {
      changeEffort(1);
      return;
    }
  }, { isActive: true });

  const effortLabel = EFFORT_LABELS[EFFORT_LEVELS[effortIndex]!] ?? "High effort";

  return (
    <Box flexDirection="column" paddingX={2} paddingY={1}>
      {/* Header */}
      <Box marginBottom={1}>
        <Text bold color="cyan">Select model</Text>
      </Box>
      <Box marginBottom={1}>
        <Text dimColor>
          Switch between available models. Your pick becomes the default for new sessions.
        </Text>
      </Box>

      {/* Model list */}
      <Box flexDirection="column" marginBottom={1}>
        {entries.map((entry, index) => {
          const isFocused = index === focusedIndex;
          const prefix = isFocused ? "❯" : " ";
          const check = entry.isCurrent ? " ✔" : "";
          const highlight = isFocused ? { color: "cyan" as const, bold: true } : undefined;

          let label = `${prefix} ${index + 1}. ${entry.displayName}${check}`;
          if (entry.isCustom) {
            label = `${prefix} ${index + 1}. ${entry.displayName} (custom)${check}`;
          }

          const ctxInfo = formatContextWindow(entry.contextWindow);
          const prov = entry.provider ? ` · ${providerLabel(entry.provider)}` : "";

          return (
            <Box key={entry.slug} flexDirection="row">
              <Text {...highlight}>{label}</Text>
              <Text dimColor>  {ctxInfo}{prov}</Text>
            </Box>
          );
        })}
      </Box>

      {/* Effort toggle */}
      <Box marginBottom={1}>
        <Text>
          {"● ".slice(0, 2)} {effortLabel}{" "}
          <Text dimColor>←/→ to adjust</Text>
        </Text>
      </Box>

      {/* Footer hints */}
      <Box>
        <Text dimColor>
          Enter to set as default · s to use this session only · Esc to cancel
        </Text>
      </Box>
    </Box>
  );
}
