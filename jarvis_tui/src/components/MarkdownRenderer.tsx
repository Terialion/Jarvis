/**
 * MarkdownRenderer — renders markdown text with Ink components.
 *
 * Handles: bold (**text**), italic (*text*), inline code (`code`),
 * bullet lists (- / *), numbered lists (1.), headings (#), code blocks (```).
 */
import React from "react";
import { Box, Text } from "ink";

function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  // Parse **bold**, *italic*, `code` in sequence
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = re.exec(text)) !== null) {
    // Text before this match
    if (match.index > last) {
      nodes.push(<Text key={key++}>{text.slice(last, match.index)}</Text>);
    }
    if (match[2]) {
      // **bold**
      nodes.push(<Text key={key++} bold>{match[2]}</Text>);
    } else if (match[3]) {
      // *italic*
      nodes.push(<Text key={key++} italic>{match[3]}</Text>);
    } else if (match[4]) {
      // `code`
      nodes.push(<Text key={key++} dimColor backgroundColor="#333">{match[4]}</Text>);
    }
    last = match.index + match[0].length;
  }

  // Remaining text
  if (last < text.length) {
    nodes.push(<Text key={key++}>{text.slice(last)}</Text>);
  }

  return nodes.length > 0 ? nodes : [<Text key="t">{text}</Text>];
}

function renderLine(line: string, key: number): React.ReactNode {
  // Empty line
  if (!line.trim()) {
    return <Box key={key} height={1} />;
  }

  // Heading
  const heading = line.match(/^(#{1,3})\s+(.+)/);
  if (heading) {
    return (
      <Box key={key}>
        <Text bold>{heading[2]}</Text>
      </Box>
    );
  }

  // Bullet list
  const bullet = line.match(/^(\s*)[-*]\s+(.+)/);
  if (bullet) {
    return (
      <Box key={key}>
        <Text>{"  ".repeat(Math.floor(bullet[1].length / 2))}  • </Text>
        <Text>{renderInline(bullet[2])}</Text>
      </Box>
    );
  }

  // Numbered list
  const numbered = line.match(/^(\s*)\d+[.)]\s+(.+)/);
  if (numbered) {
    const indent = Math.floor(numbered[1].length / 2);
    return (
      <Box key={key}>
        <Text>{"  ".repeat(indent)}  ▸ </Text>
        <Text>{renderInline(numbered[2])}</Text>
      </Box>
    );
  }

  // Horizontal rule
  if (line.match(/^[-*_]{3,}\s*$/)) {
    return (
      <Box key={key}>
        <Text dimColor>{"─".repeat(40)}</Text>
      </Box>
    );
  }

  // Regular paragraph
  return (
    <Box key={key}>
      <Text>{renderInline(line)}</Text>
    </Box>
  );
}

interface MarkdownRendererProps {
  content: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  const lines = content.split("\n");

  // Detect code blocks and wrap them
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let key = 0;

  for (const line of lines) {
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        // End code block
        elements.push(
          <Box key={key++} flexDirection="column" marginY={1} paddingLeft={2}>
            {codeLines.map((cl, i) => (
              <Text key={i} dimColor>{cl}</Text>
            ))}
          </Box>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
    } else {
      elements.push(renderLine(line, key++));
    }
  }

  // Unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    elements.push(
      <Box key={key++} flexDirection="column" marginY={1} paddingLeft={2}>
        {codeLines.map((cl, i) => (
          <Text key={i} dimColor>{cl}</Text>
        ))}
      </Box>
    );
  }

  return <Box flexDirection="column">{elements}</Box>;
};
