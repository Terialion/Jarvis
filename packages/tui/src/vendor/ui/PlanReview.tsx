import { Box, Text } from "../ink-renderer/index.js";
import type React from "react";

export interface PlanReviewRequest {
  summary: string;
  steps: Array<{ step: string; files?: string[]; verification?: string }>;
  allowedPrompts?: Array<{ tool: string; prompt: string }>;
}

export type PlanReviewDecision = "proceed" | "edit" | "cancel";

export type PlanReviewProps = {
  plan: PlanReviewRequest;
  selectedIndex: number;
};

export function PlanReview({ plan, selectedIndex }: PlanReviewProps): React.ReactNode {
  const options = [
    { label: "Yes, proceed", description: "Approve and start implementation" },
    { label: "Edit plan first", description: "Make changes before proceeding" },
    { label: "Cancel", description: "Discard this plan" },
  ];

  return (
    <Box flexDirection="column" paddingX={2} paddingY={1} borderStyle="round" borderColor="#E6B450">
      <Box marginBottom={1}>
        <Text bold color="#E6B450">
          Plan: {plan.summary}
        </Text>
      </Box>

      {(plan.steps as Array<{ step: string; files?: string[]; verification?: string }>).map((s, i) => {
        const files = s.files?.length ? ` [${s.files.join(", ")}]` : "";
        const verify = s.verification ? ` → verify: ${s.verification}` : "";
        return (
          <Box key={i}>
            <Text>
              {"  "}
              {i + 1}. {s.step}
            </Text>
            <Text dimColor>
              {files}
              {verify}
            </Text>
          </Box>
        );
      })}

      {plan.allowedPrompts && plan.allowedPrompts.length > 0 && (
        <Box marginTop={1} flexDirection="column">
          <Text dimColor>Required permissions:</Text>
          {plan.allowedPrompts.map((p, i) => (
            <Text key={i} dimColor>
              {"  "}
              {p.tool}: {p.prompt}
            </Text>
          ))}
        </Box>
      )}

      <Box marginTop={1}>
        <Text dimColor>──────────────────────────────────────────────</Text>
      </Box>

      <Box marginTop={1}>
        <Text bold>Proceed with implementation?</Text>
      </Box>

      <Box flexDirection="column" marginTop={1}>
        {options.map((opt, i) => (
          <Box key={i}>
            <Text color={selectedIndex === i ? "#E6B450" : undefined}>
              {selectedIndex === i ? "❯" : " "} {i + 1}. {opt.label}
            </Text>
            <Text dimColor> — {opt.description}</Text>
          </Box>
        ))}
      </Box>

      <Box marginTop={1}>
        <Text dimColor>Enter to confirm · Esc to cancel</Text>
      </Box>
    </Box>
  );
}
