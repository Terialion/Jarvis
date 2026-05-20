import React, { useState } from "react";
import { Box, Text } from "ink";
import type { FileChange } from "../types.js";

interface DiffBlockProps {
  change: FileChange;
}

const COLLAPSE_THRESHOLD = 20;
const PREVIEW_LINES = 10;

export const DiffBlock: React.FC<DiffBlockProps> = ({ change }) => {
  const [expanded, setExpanded] = useState(false);
  const lines = change.diff_text.split("\n");
  const totalLines = lines.length;
  const shouldCollapse = totalLines > COLLAPSE_THRESHOLD && !expanded;
  const visibleLines = shouldCollapse ? lines.slice(0, PREVIEW_LINES) : lines;

  // Count actual additions/removals for collapsed preview
  const allAdded = lines.filter(l => l.startsWith("+") && !l.startsWith("+++")).length;
  const allRemoved = lines.filter(l => l.startsWith("-") && !l.startsWith("---")).length;

  return (
    <Box flexDirection="column" marginY={1}>
      {/* Header: file path + stats */}
      <Box>
        <Text color="cyan" bold>
          {change.status === "created" ? "Created" : "Modified"}:{" "}
        </Text>
        <Text>{change.path}</Text>
        <Text dimColor>
          {" "}(+{allAdded} -{allRemoved})
        </Text>
      </Box>

      {/* Diff lines: sign │ content */}
      {visibleLines.map((line, i) => {
        const prefix = line.charAt(0);
        let contentColor: string | undefined;
        if (prefix === "+" && !line.startsWith("+++")) {
          contentColor = "green";
        } else if (prefix === "-" && !line.startsWith("---")) {
          contentColor = "red";
        }

        return (
          <Box key={i} flexDirection="row">
            <Text dimColor={!contentColor} color={contentColor}>
              {prefix}
            </Text>
            <Text color={contentColor} dimColor={!contentColor}>
              {line.slice(1)}
            </Text>
          </Box>
        );
      })}

      {/* Collapse hint */}
      {totalLines > COLLAPSE_THRESHOLD && !expanded && (
        <Box>
          <Text dimColor>
            ─ {totalLines - PREVIEW_LINES} more lines ─
          </Text>
        </Box>
      )}
      {expanded && totalLines > COLLAPSE_THRESHOLD && (
        <Box>
          <Text dimColor>
            ─ {totalLines} lines total ─
          </Text>
        </Box>
      )}
    </Box>
  );
};
