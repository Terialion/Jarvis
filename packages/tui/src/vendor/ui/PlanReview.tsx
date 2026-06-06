import { Box, Text, useInput } from '../ink-renderer/index.js';
import React, { useState } from 'react';

export interface PlanReviewRequest {
  summary: string;
  steps: Array<{ step: string; files?: string[]; verification?: string }>;
  allowedPrompts?: Array<{ tool: string; prompt: string }>;
}

export type PlanReviewDecision = 'proceed' | 'edit' | 'cancel';

export type PlanReviewProps = {
  plan: PlanReviewRequest;
  selectedIndex: number;
};

const OPTIONS = [
  { value: 'proceed' as const, label: 'Approve', key: 'y', description: 'Start implementation' },
  { value: 'edit' as const, label: 'Edit', key: 'e', description: 'Request changes' },
  { value: 'cancel' as const, label: 'Cancel', key: 'n', description: 'Discard plan' },
];

export function PlanReview({ plan, selectedIndex }: PlanReviewProps): React.ReactNode {
  const [focusIndex, setFocusIndex] = useState(selectedIndex);

  useInput((input, key) => {
    if (input === 'y') {
      // Trigger proceed via parent callback — handled by REPL keybinding
      return;
    }
    if (input === 'e') {
      return;
    }
    if (input === 'n' || key.escape) {
      return;
    }
    if (key.upArrow || input === 'k') {
      setFocusIndex((prev) => (prev - 1 + OPTIONS.length) % OPTIONS.length);
    } else if (key.downArrow || input === 'j') {
      setFocusIndex((prev) => (prev + 1) % OPTIONS.length);
    }
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Compact header: summary + step count */}
      <Box>
        <Text bold color="#E6B450">Plan</Text>
        <Text dimColor> — </Text>
        <Text>{plan.summary}</Text>
        <Text dimColor> ({plan.steps.length} step{plan.steps.length === 1 ? '' : 's'})</Text>
      </Box>

      {/* Steps (compact, one line each) */}
      <Box flexDirection="column" marginLeft={2} marginTop={0}>
        {plan.steps.map((step, index) => {
          const meta = [
            step.files?.length ? `${step.files.length} file${step.files.length === 1 ? '' : 's'}` : '',
            step.verification ? '✓' : '',
          ].filter(Boolean).join(' · ');
          return (
            <Text key={index}>
              <Text dimColor>{`${index + 1}. `}</Text>
              <Text>{step.step}</Text>
              {meta ? <Text dimColor>{` (${meta})`}</Text> : null}
            </Text>
          );
        })}
      </Box>

      {/* Options: vertical list */}
      <Box marginTop={1} flexDirection="column">
        {OPTIONS.map((opt, i) => {
          const isFocused = i === focusIndex;
          return (
            <Box key={opt.value}>
              <Text color={isFocused ? '#E6B450' : undefined}>{isFocused ? '❯' : ' '}</Text>
              <Text color={isFocused ? '#E6B450' : undefined} bold={isFocused}>
                {opt.key}
              </Text>
              <Text dimColor>{') '}</Text>
              <Text color={isFocused ? '#E6B450' : undefined}>
                {opt.label}
              </Text>
              <Text dimColor> — {opt.description}</Text>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}
