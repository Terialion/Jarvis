/**
 * ToggleBlock — renders the thinking/tools toggle hint below the answer.
 */
import React from "react";
import { Box, Text } from "ink";

interface ToggleBlockProps {
  hasThinking: boolean;
  hasTools: boolean;
  thinkingExpanded: boolean;
  toolsExpanded: boolean;
}

export const ToggleBlock: React.FC<ToggleBlockProps> = ({
  hasThinking,
  hasTools,
  thinkingExpanded,
  toolsExpanded,
}) => {
  if (!hasThinking && !hasTools) return null;

  const hints: string[] = [];
  if (hasThinking) {
    hints.push(`Ctrl+T ${thinkingExpanded ? "collapse" : "expand"} thinking`);
  }
  if (hasTools) {
    hints.push(`Ctrl+O ${toolsExpanded ? "collapse" : "expand"} tools`);
  }

  return (
    <Box height={1} flexShrink={0}>
      <Text dimColor>  {hints.join(" · ")}</Text>
    </Box>
  );
};
