import { Box, Text } from '../ink-renderer/index.js';
import type React from 'react';

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

export function PlanReview({ plan, selectedIndex }: PlanReviewProps): React.ReactNode {
  const options = [
    { label: 'Proceed', description: 'Approve and start implementation' },
    { label: 'Edit first', description: 'Ask for changes before proceeding' },
    { label: 'Cancel', description: 'Discard this plan for now' },
  ];

  return (
    <Box flexDirection="column" paddingX={1} paddingY={1} borderStyle="round" borderColor="#E6B450">
      <Text bold color="#E6B450">
        Task Sidebar
      </Text>

      <Box marginTop={1} flexDirection="column">
        <Text bold>{plan.summary}</Text>
        <Text dimColor>{`${plan.steps.length} step${plan.steps.length === 1 ? '' : 's'}`}</Text>
      </Box>

      <Box marginTop={1} flexDirection="column">
        {plan.steps.map((step, index) => {
          const meta = [
            step.files?.length ? `${step.files.length} file${step.files.length === 1 ? '' : 's'}` : '',
            step.verification ? 'has verification' : '',
          ]
            .filter(Boolean)
            .join(' · ');
          return (
            <Box key={index} flexDirection="column" marginBottom={index === plan.steps.length - 1 ? 0 : 1}>
              <Text>{`${index + 1}. ${step.step}`}</Text>
              {meta ? <Text dimColor>{meta}</Text> : null}
            </Box>
          );
        })}
      </Box>

      {plan.allowedPrompts && plan.allowedPrompts.length > 0 ? (
        <Box marginTop={1} flexDirection="column">
          <Text dimColor>Required permissions</Text>
          {plan.allowedPrompts.map((prompt, index) => (
            <Text key={index} dimColor>{`${prompt.tool}: ${prompt.prompt}`}</Text>
          ))}
        </Box>
      ) : null}

      <Box marginTop={1}>
        <Text dimColor>────────────────────────</Text>
      </Box>

      <Box marginTop={1} flexDirection="column">
        <Text bold>Review options</Text>
        {options.map((option, index) => (
          <Box key={index} flexDirection="column" marginTop={1}>
            <Text color={selectedIndex === index ? '#E6B450' : undefined} bold={selectedIndex === index}>
              {`${selectedIndex === index ? '> ' : '  '}${option.label}`}
            </Text>
            <Text dimColor>{option.description}</Text>
          </Box>
        ))}
      </Box>

      <Box marginTop={1}>
        <Text dimColor>Enter to confirm · Esc to cancel · j/k to move</Text>
      </Box>
    </Box>
  );
}
