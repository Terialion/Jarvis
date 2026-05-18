/**
 * MarkdownRenderer — renders markdown text with Ink components.
 *
 * Handles: tables (|...|), bold (**text**), italic (*text*), inline code (`code`),
 * bullet lists (- / *), numbered lists (1.), headings (#), code blocks (```).
 *
 * All React keys use prefixed strings (l-, t-, tc-, ts-, il-) to prevent
 * cross-namespace collisions that cause "Encountered two children with the
 * same key" warnings.
 */
import React from "react";
import { Box, Text } from "ink";

// ── Inline formatting ──────────────────────────────────────────────

function renderInline(text: string, prefix: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = [];
  const re = /(\*\*(.+?)\*\*|\*(.+?)\*|`([^`]+)`)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let n = 0;

  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      nodes.push(<Text key={`${prefix}-${n++}`}>{text.slice(last, match.index)}</Text>);
    }
    if (match[2]) {
      nodes.push(<Text key={`${prefix}-${n++}`} bold>{match[2]}</Text>);
    } else if (match[3]) {
      nodes.push(<Text key={`${prefix}-${n++}`} italic>{match[3]}</Text>);
    } else if (match[4]) {
      nodes.push(<Text key={`${prefix}-${n++}`} dimColor>{match[4]}</Text>);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    nodes.push(<Text key={`${prefix}-${n++}`}>{text.slice(last)}</Text>);
  }
  return nodes.length > 0 ? nodes : [<Text key={`${prefix}-0`}>{text}</Text>];
}

// ── Unicode display width ──────────────────────────────────────────

function displayWidth(s: string): number {
  let w = 0;
  for (const ch of s) {
    const cp = ch.codePointAt(0) ?? 0;
    if ((cp >= 0x1100 && cp <= 0x115f) ||
        (cp >= 0x2e80 && cp <= 0xa4cf) ||
        (cp >= 0xac00 && cp <= 0xd7a3) ||
        (cp >= 0xf900 && cp <= 0xfaff) ||
        (cp >= 0xfe30 && cp <= 0xfe6f) ||
        (cp >= 0xff01 && cp <= 0xff60) ||
        (cp >= 0xffe0 && cp <= 0xffe6) ||
        (cp >= 0x1f300 && cp <= 0x1f9ff) ||
        (cp >= 0x1fa00 && cp <= 0x1fa6f) ||
        (cp >= 0x20000 && cp <= 0x2fffd) ||
        (cp >= 0x30000 && cp <= 0x3fffd)) {
      w += 2;
    } else if (cp < 0x20 || (cp >= 0x7f && cp <= 0x9f)) {
      // Control chars: zero width
    } else {
      w += 1;
    }
  }
  return w;
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

function renderTable(lines: string[], keyPrefix: string): { elements: React.ReactNode[]; consumed: number } {
  if (lines.length < 2) return { elements: [], consumed: 0 };

  if (!isTableRow(lines[0]) || !isTableSep(lines[1])) {
    return { elements: [], consumed: 0 };
  }

  const header = parseTableRow(lines[0]);
  const colCount = header.length;

  const dataRows: string[][] = [];
  let consumed = 2;
  while (consumed < lines.length && isTableRow(lines[consumed])) {
    const cells = parseTableRow(lines[consumed]);
    while (cells.length < colCount) cells.push("");
    dataRows.push(cells.slice(0, colCount));
    consumed++;
  }

  const colWidths = header.map((h, i) => {
    let w = displayWidth(h);
    for (const row of dataRows) {
      w = Math.max(w, displayWidth(row[i] ?? ""));
    }
    return Math.min(w, 36);
  });

  const elements: React.ReactNode[] = [];
  let k = 0;

  function renderCell(content: string, width: number, header: boolean): React.ReactNode {
    const cellKey = `${keyPrefix}-tc-${k++}`;
    return (
      <Box key={cellKey} width={width}>
        {header ? (
          <Text bold>{renderInline(content, cellKey)}</Text>
        ) : (
          <Text>{renderInline(content, cellKey)}</Text>
        )}
      </Box>
    );
  }

  function renderSep(i: number): React.ReactNode {
    if (i >= colCount - 1) return null;
    return <Text key={`${keyPrefix}-ts-${k++}`} dimColor> │ </Text>;
  }

  // Top border
  elements.push(
    <Box key={`${keyPrefix}-top`}>
      <Text dimColor>┌─</Text>
      {colWidths.map((w, i) => (
        <React.Fragment key={`${keyPrefix}-topf-${i}`}>
          <Text dimColor>{"─".repeat(Math.max(w, 1))}</Text>
          {i < colCount - 1 ? <Text dimColor>─┬─</Text> : null}
        </React.Fragment>
      ))}
      <Text dimColor>─┐</Text>
    </Box>
  );

  // Header row
  elements.push(
    <Box key={`${keyPrefix}-head`}>
      <Text dimColor>│ </Text>
      {header.map((h, i) => (
        <React.Fragment key={`${keyPrefix}-hf-${i}`}>
          {renderCell(h, colWidths[i], true)}
          {renderSep(i)}
        </React.Fragment>
      ))}
      <Text dimColor> │</Text>
    </Box>
  );

  // Separator row
  elements.push(
    <Box key={`${keyPrefix}-sep`}>
      <Text dimColor>├─</Text>
      {colWidths.map((w, i) => (
        <React.Fragment key={`${keyPrefix}-sepf-${i}`}>
          <Text dimColor>{"─".repeat(Math.max(w, 1))}</Text>
          {i < colCount - 1 ? <Text dimColor>─┼─</Text> : null}
        </React.Fragment>
      ))}
      <Text dimColor>─┤</Text>
    </Box>
  );

  // Data rows
  for (let ri = 0; ri < dataRows.length; ri++) {
    const row = dataRows[ri];
    elements.push(
      <Box key={`${keyPrefix}-row-${ri}`}>
        <Text dimColor>│ </Text>
        {row.map((cell, i) => {
          if (i >= colCount) return null;
          return (
            <React.Fragment key={`${keyPrefix}-rf-${ri}-${i}`}>
              {renderCell(cell, colWidths[i], false)}
              {renderSep(i)}
            </React.Fragment>
          );
        })}
        <Text dimColor> │</Text>
      </Box>
    );
  }

  // Bottom border
  elements.push(
    <Box key={`${keyPrefix}-bot`}>
      <Text dimColor>└─</Text>
      {colWidths.map((w, i) => (
        <React.Fragment key={`${keyPrefix}-botf-${i}`}>
          <Text dimColor>{"─".repeat(Math.max(w, 1))}</Text>
          {i < colCount - 1 ? <Text dimColor>─┴─</Text> : null}
        </React.Fragment>
      ))}
      <Text dimColor>─┘</Text>
    </Box>
  );

  return { elements, consumed };
}

// ── Line renderer ───────────────────────────────────────────────────

function renderLine(line: string, keyPrefix: string): React.ReactNode {
  if (!line.trim()) {
    return <Box key={keyPrefix} height={1} />;
  }

  // Heading
  const heading = line.match(/^(#{1,3})\s+(.+)/);
  if (heading) {
    return (
      <Box key={keyPrefix}>
        <Text bold>{heading[2]}</Text>
      </Box>
    );
  }

  // Bullet list
  const bullet = line.match(/^(\s*)[-*]\s+(.+)/);
  if (bullet) {
    return (
      <Box key={keyPrefix}>
        <Text>{"  ".repeat(Math.floor(bullet[1].length / 2))}  • </Text>
        <Text>{renderInline(bullet[2], `${keyPrefix}-il`)}</Text>
      </Box>
    );
  }

  // Numbered list
  const numbered = line.match(/^(\s*)\d+[.)]\s+(.+)/);
  if (numbered) {
    const indent = Math.floor(numbered[1].length / 2);
    return (
      <Box key={keyPrefix}>
        <Text>{"  ".repeat(indent)}  ▸ </Text>
        <Text>{renderInline(numbered[2], `${keyPrefix}-il`)}</Text>
      </Box>
    );
  }

  // Horizontal rule
  if (line.match(/^[-*_]{3,}\s*$/)) {
    return (
      <Box key={keyPrefix}>
        <Text dimColor>{"─".repeat(40)}</Text>
      </Box>
    );
  }

  // Blockquote
  const quote = line.match(/^>\s?(.+)/);
  if (quote) {
    return (
      <Box key={keyPrefix}>
        <Text dimColor>│ </Text>
        <Text>{renderInline(quote[1], `${keyPrefix}-il`)}</Text>
      </Box>
    );
  }

  return (
    <Box key={keyPrefix}>
      <Text>{renderInline(line, `${keyPrefix}-il`)}</Text>
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
  let lineNum = 0;
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    // Code block
    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        elements.push(
          <Box key={`cb-${lineNum++}`} flexDirection="column" marginY={1} paddingLeft={2}>
            {codeLines.map((cl, ci) => (
              <Text key={`cb-${lineNum}-${ci}`} dimColor>{cl}</Text>
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
    const table = renderTable(lines.slice(i), `t-${lineNum}`);
    if (table.consumed > 0) {
      elements.push(...table.elements);
      lineNum++;
      i += table.consumed;
      continue;
    }

    // Regular line
    elements.push(renderLine(line, `l-${lineNum++}`));
    i++;
  }

  // Unclosed code block
  if (inCodeBlock && codeLines.length > 0) {
    elements.push(
      <Box key={`cb-${lineNum++}`} flexDirection="column" marginY={1} paddingLeft={2}>
        {codeLines.map((cl, ci) => (
          <Text key={`cb-${lineNum}-${ci}`} dimColor>{cl}</Text>
        ))}
      </Box>
    );
  }

  return <Box flexDirection="column">{elements}</Box>;
};
