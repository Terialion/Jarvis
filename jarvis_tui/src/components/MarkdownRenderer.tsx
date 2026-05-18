/**
 * MarkdownRenderer — renders markdown text with Ink components.
 *
 * Handles: tables (|...|), bold (**text**), italic (*text*), inline code (`code`),
 * bullet lists (- / *), numbered lists (1.), headings (#), code blocks (```).
 */
import React from "react";
import { Box, Text } from "ink";

// ── Inline formatting ──────────────────────────────────────────────

function renderInline(text: string, keyOffset = 0): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = keyOffset;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(<Text key={key++}>{text.slice(last, match.index)}</Text>);
    }
    if (match[2]) {
      nodes.push(<Text key={key++} bold>{match[2]}</Text>);
    } else if (match[3]) {
      nodes.push(<Text key={key++} italic>{match[3]}</Text>);
    } else if (match[4]) {
      nodes.push(<Text key={key++} dimColor>{match[4]}</Text>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    nodes.push(<Text key={key++}>{text.slice(last)}</Text>);
  }
  return nodes.length > 0 ? nodes : [<Text key={keyOffset}>{text}</Text>];
}

// ── Table rendering ────────────────────────────────────────────────

function isTableRow(line: string): boolean {
  return /^\|.+\|$/.test(line.trim());
}

function isTableSep(line: string): boolean {
  return /^\|[\s\-:]+\|[\s\-:|]+\|$/.test(line.trim());
}

function parseTableRow(line: string): string[] {
  return line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((c) => c.trim());
}

function renderTable(lines: string[], startKey: number): { elements: React.ReactNode[]; consumed: number } {
  if (lines.length < 2) return { elements: [], consumed: 0 };

  // First line must be header
  if (!isTableRow(lines[0]) || !isTableSep(lines[1])) {
    return { elements: [], consumed: 0 };
  }

  const header = parseTableRow(lines[0]);
  const colCount = header.length;

  // Collect data rows
  const dataRows: string[][] = [];
  let consumed = 2; // header + separator
  while (consumed < lines.length && isTableRow(lines[consumed])) {
    const cells = parseTableRow(lines[consumed]);
    // Pad to match header column count
    while (cells.length < colCount) cells.push("");
    dataRows.push(cells.slice(0, colCount));
    consumed++;
  }

  // Calculate column widths
  const colWidths = header.map((h, i) => {
    let w = h.length;
    for (const row of dataRows) {
      // Approximate width: CJK chars count as 2
      const cellW = [...row[i] ?? ""].reduce((acc, ch) => acc + (ch.charCodeAt(0) > 0x7f ? 2 : 1), 0);
      w = Math.max(w, cellW);
    }
    return Math.min(w, 30); // cap column width
  });

  // Build table elements
  const elements: React.ReactNode[] = [];
  let key = startKey;

  // Render helper: pad a string value to a target display width
  function padCell(val: string, targetWidth: number): string {
    const displayWidth = [...val].reduce((acc, ch) => acc + (ch.charCodeAt(0) > 0x7f ? 2 : 1), 0);
    const pad = targetWidth - displayWidth;
    return pad > 0 ? val + " ".repeat(pad) : val;
  }

  // Header row
  const headerCells: React.ReactNode[] = [];
  header.forEach((h, i) => {
    const padded = padCell(h, colWidths[i]);
    headerCells.push(<Text key={key++} bold>{padded}</Text>);
    if (i < colCount - 1) headerCells.push(<Text key={key++} dimColor> │ </Text>);
  });
  elements.push(
    <Box key={key++}>
      <Text dimColor>┌</Text>
      {colWidths.map((w, i) => (
        <React.Fragment key={i}>
          <Text dimColor>{"─".repeat(Math.max(w, 3))}</Text>
          {i < colCount - 1 ? <Text dimColor>─┬─</Text> : null}
        </React.Fragment>
      ))}
      <Text dimColor>┐</Text>
    </Box>
  );

  // Simplified: render header and rows as plain aligned text
  // (avoiding complex box layout issues)
  elements.push(
    <Box key={key++}>
      <Text dimColor>│ </Text>
      {headerCells}
      <Text dimColor> │</Text>
    </Box>
  );

  // Separator
  elements.push(
    <Box key={key++}>
      <Text dimColor>├</Text>
      {colWidths.map((w, i) => (
        <React.Fragment key={i}>
          <Text dimColor>{"─".repeat(Math.max(w, 3))}</Text>
          {i < colCount - 1 ? <Text dimColor>─┼─</Text> : null}
        </React.Fragment>
      ))}
      <Text dimColor>┤</Text>
    </Box>
  );

  // Data rows
  for (const row of dataRows) {
    const cells: React.ReactNode[] = [];
    row.forEach((cell, i) => {
      if (i >= colCount) return;
      const padded = padCell(cell, colWidths[i]);
      cells.push(<Text key={key++}>{padded}</Text>);
      if (i < colCount - 1) cells.push(<Text key={key++} dimColor> │ </Text>);
    });
    elements.push(
      <Box key={key++}>
        <Text dimColor>│ </Text>
        {cells}
        <Text dimColor> │</Text>
      </Box>
    );
  }

  // Bottom border
  elements.push(
    <Box key={key++}>
      <Text dimColor>└</Text>
      {colWidths.map((w, i) => (
        <React.Fragment key={i}>
          <Text dimColor>{"─".repeat(Math.max(w, 3))}</Text>
          {i < colCount - 1 ? <Text dimColor>─┴─</Text> : null}
        </React.Fragment>
      ))}
      <Text dimColor>┘</Text>
    </Box>
  );

  return { elements, consumed };
}

// ── Line renderer ───────────────────────────────────────────────────

function renderLine(line: string, key: number): React.ReactNode {
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
        <Text>{renderInline(bullet[2], key * 100)}</Text>
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
        <Text>{renderInline(numbered[2], key * 100)}</Text>
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

  // Blockquote
  const quote = line.match(/^>\s?(.+)/);
  if (quote) {
    return (
      <Box key={key}>
        <Text dimColor>│ </Text>
        <Text>{renderInline(quote[1], key * 100)}</Text>
      </Box>
    );
  }

  return (
    <Box key={key}>
      <Text>{renderInline(line, key * 100)}</Text>
    </Box>
  );
}

// ── Main component ──────────────────────────────────────────────────

interface MarkdownRendererProps {
  content: string;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  const lines = content.split("\n");
  const elements: React.ReactNode[] = [];
  let inCodeBlock = false;
  let codeLines: string[] = [];
  let key = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <Box key={key++} flexDirection="column" marginY={1} paddingLeft={2}>
            {codeLines.map((cl, ci) => (
              <Text key={ci} dimColor>{cl}</Text>
            ))}
          </Box>
        );
        codeLines = [];
        inCodeBlock = false;
      } else {
        inCodeBlock = true;
      }
      i++;
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(line);
      i++;
      continue;
    }

    // Try table
    const table = renderTable(lines.slice(i), key);
    if (table.consumed > 0) {
      elements.push(...table.elements);
      key += table.elements.length;
      i += table.consumed;
      continue;
    }

    // Regular line
    elements.push(renderLine(line, key++));
    i++;
  }

  // Unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    elements.push(
      <Box key={key++} flexDirection="column" marginY={1} paddingLeft={2}>
        {codeLines.map((cl, ci) => (
          <Text key={ci} dimColor>{cl}</Text>
        ))}
      </Box>
    );
  }

  return <Box flexDirection="column">{elements}</Box>;
};
