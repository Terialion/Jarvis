import { Box, Text } from '../vendor/ink-renderer/index.js';
import type React from 'react';
import { Markdown } from '../vendor/ui/Markdown.js';
import { decodeHtmlEntities } from '../vendor/ui/utils/markdown.js';
import type {
  CodexTimelineItemView,
  CodexTimelineSearchState,
  CodexTimelineState,
  CodexTimelineTurnView,
} from './codex-timeline-state.js';

function ItemHeader({
  marker,
  track = '|',
  trackColor = '#4B5563',
  markerColor,
  label,
  meta,
  active = false,
}: {
  marker: string;
  track?: string;
  trackColor?: string;
  markerColor: string;
  label: string;
  meta?: string;
  active?: boolean;
}): React.ReactNode {
  return (
    <Box>
      <Text color={active ? '#7AA2F7' : trackColor}>{`${active ? '>' : track} `}</Text>
      <Text color={active ? '#7AA2F7' : markerColor}>{marker}</Text>
      <Text bold color={active ? '#C6D9FF' : undefined}>{` ${label}`}</Text>
      {meta ? <Text dimColor>{` | ${meta}`}</Text> : null}
    </Box>
  );
}

function SearchHit({ excerpt, marginLeft = 4 }: { excerpt?: string | null; marginLeft?: number }): React.ReactNode {
  if (!excerpt) return null;
  return (
    <Box marginLeft={marginLeft}>
      <Text color="#7AA2F7" dimColor>{`match | ${decodeHtmlEntities(excerpt)}`}</Text>
    </Box>
  );
}

function ExpandHint({ expanded, marginLeft = 4 }: { expanded: boolean; marginLeft?: number }): React.ReactNode {
  return (
    <Box marginLeft={marginLeft}>
      <Text dimColor>{expanded ? 'Ctrl+O to collapse details' : 'Ctrl+O to inspect details'}</Text>
    </Box>
  );
}

function DetailLine({
  text,
  color,
  backgroundColor,
  bold = false,
  dim = false,
  prefix,
}: {
  text: string;
  color?: string;
  backgroundColor?: string;
  bold?: boolean;
  dim?: boolean;
  /** Custom prefix to replace the default "| " gutter. */
  prefix?: string;
}): React.ReactNode {
  const decoded = decodeHtmlEntities(text);
  const gutter = prefix !== undefined ? prefix : '| ';
  return (
    <Box marginLeft={4}>
      <Text color="#4B5563">{gutter}</Text>
      <Text bold={bold} color={color} backgroundColor={backgroundColor} dimColor={dim}>{` ${decoded} `}</Text>
    </Box>
  );
}

function SummaryCard({
  text,
  color,
  backgroundColor,
  borderColor,
}: {
  text: string;
  color: string;
  backgroundColor: string;
  borderColor: string;
}): React.ReactNode {
  const decoded = decodeHtmlEntities(text);
  return (
    <Box marginLeft={4}>
      <Text color="#4B5563">{'| '}</Text>
      <Box borderStyle="round" borderColor={borderColor} paddingX={1} backgroundColor={backgroundColor}>
        <Text color={color} bold>{decoded}</Text>
      </Box>
    </Box>
  );
}

function getPreviewLineStyle(line: string): {
  color?: string;
  backgroundColor?: string;
  bold?: boolean;
  dim?: boolean;
} {
  // Match diff lines with line numbers: "  42 - content" or "  42 + content"
  const trimmed = line.trimStart();
  if (trimmed.includes(' - ') || trimmed.startsWith('- ')) {
    // Softer red/purple lane, closer to muted status accents.
    return { color: '#D39AC1', backgroundColor: '#3A2A36', bold: false, dim: false };
  }
  if (trimmed.includes(' + ') || trimmed.startsWith('+ ')) {
    // Softer green lane, close to "state Ready" family.
    return { color: '#80C99A', backgroundColor: '#20362B', bold: false, dim: false };
  }
  // Neutral code lane.
  return { color: '#C8D3E8', backgroundColor: '#2A313E', dim: false };
}

function getCollapsedDetailStyle(item: Extract<CodexTimelineItemView, { kind: 'tool_call' }>): {
  color?: string;
  backgroundColor?: string;
  borderColor?: string;
  bold?: boolean;
  dim?: boolean;
} {
  if (item.status === 'failed') {
    return { color: 'red', bold: true, dim: false };
  }
  if (item.label.startsWith('Update(') || item.label.startsWith('Write(')) {
    return {
      color: '#C8D3E8',
      backgroundColor: '#2A313E',
      bold: false,
      dim: false,
    };
  }
  return { dim: true };
}

function summarizeText(text: string, limit = 120): string {
  const compact = decodeHtmlEntities(text).replace(/\s+/g, ' ').trim();
  if (compact.length <= limit) return compact;
  return `${compact.slice(0, limit)}...`;
}

function summarizeLines(lines: string[], limit = 2): string[] {
  return lines.slice(0, limit).map((line) => summarizeText(line, 120));
}

function TurnHeader({ turn, active }: { turn: CodexTimelineTurnView; active?: boolean }): React.ReactNode {
  const markerColor =
    turn.status === 'failed' ? 'red' : turn.status === 'completed' ? '#5FA8D3' : '#C59A6D';
  const itemCount = turn.items.length;
  const itemMeta = itemCount === 1 ? '1 item' : `${itemCount} items`;
  return (
    <Box>
      <Text color={active ? '#7AA2F7' : markerColor}>{active ? '>' : '|'}</Text>
      <Text bold color={active ? '#C6D9FF' : '#5FA8D3'}>{` Turn ${turn.turnNumber}`}</Text>
      <Text dimColor>{` | ${turn.statusText}`}</Text>
      <Text dimColor>{` | ${itemMeta}`}</Text>
      {turn.statsText ? <Text dimColor>{` | ${turn.statsText}`}</Text> : null}
    </Box>
  );
}

function TimelineItemView({
  item,
  active,
  excerpt,
  detailsExpanded = false,
}: {
  item: CodexTimelineItemView;
  active?: boolean;
  excerpt?: string | null;
  detailsExpanded?: boolean;
}): React.ReactNode {
  switch (item.kind) {
    case 'reasoning':
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1}>
          <ItemHeader marker=">" markerColor="#C59A6D" label={item.label} meta={item.meta} active={active} />
          <SearchHit excerpt={excerpt} marginLeft={4} />
          <ExpandHint expanded={detailsExpanded} />
          <DetailLine text={detailsExpanded ? item.text : summarizeText(item.text, 160)} dim />
        </Box>
      );
    case 'agent_message':
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1}>
          <ItemHeader marker="o" markerColor="#DA7756" label={item.label} meta={item.meta} active={active} />
          <SearchHit excerpt={excerpt} marginLeft={4} />
          <Box marginLeft={4}>
            <Text color="#4B5563">{'| '}</Text>
            <Markdown>{item.text}</Markdown>
          </Box>
        </Box>
      );
    case 'tool_call':
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1}>
          <ItemHeader
            marker="*"
            markerColor={item.status === 'failed' ? 'red' : item.status === 'completed' ? 'green' : 'yellow'}
            label={item.label}
            meta={item.statusLabel}
            active={active}
          />
          <SearchHit excerpt={excerpt} marginLeft={4} />
          {!item.alwaysShowPreview && <ExpandHint expanded={detailsExpanded} />}
          {item.collapsedDetail ? (() => {
            const style = getCollapsedDetailStyle(item);
            return (
              <DetailLine
                text={item.collapsedDetail}
                color={style.color}
                backgroundColor={style.backgroundColor}
                bold={style.bold}
                dim={style.dim}
              />
            );
          })() : null}
          {(item.alwaysShowPreview || detailsExpanded) &&
            item.previewLines?.map((line, index) => {
              const style = getPreviewLineStyle(line);
              const lines = item.previewLines ?? [];
              const totalLines = lines.length + (item.previewOverflowCount ?? 0);
              const pad = String(totalLines).length;
              const lineNum = String(index + 1).padStart(pad);
              let prefix: string | undefined;
              if (item.previewKind === 'code') {
                prefix = `${lineNum} `;
              } else if (item.previewKind === 'diff') {
                prefix = '';  // No gutter for diff — line numbers are in the text
              }
              return (
                <DetailLine
                  key={`${item.id}-preview-${index}`}
                  text={line}
                  color={style.color}
                  backgroundColor={style.backgroundColor}
                  bold={style.bold}
                  dim={style.dim}
                  prefix={prefix}
                />
              );
            })}
          {(item.alwaysShowPreview || detailsExpanded) && (item.previewOverflowCount ?? 0) > 0 ? (
            <DetailLine
              text={
                detailsExpanded || item.alwaysShowPreview
                  ? `... +${item.previewOverflowCount} more lines`
                  : `... +${item.previewOverflowCount} lines (Ctrl+O to expand)`
              }
              dim
            />
          ) : null}
          {detailsExpanded && item.argumentsText ? <DetailLine text={`args | ${item.argumentsText}`} dim /> : null}
          {detailsExpanded &&
          item.resultText &&
          item.resultText !== item.collapsedDetail?.replace(/^done \| /, '') ? (
            <DetailLine text={`result | ${item.resultText}`} dim />
          ) : null}
          {detailsExpanded &&
          item.errorText &&
          item.errorText !== item.collapsedDetail?.replace(/^failed \| /, '') ? (
            <DetailLine text={`error | ${item.errorText}`} color="red" />
          ) : null}
        </Box>
      );
    case 'todo_list':
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1}>
          <ItemHeader marker="=" markerColor="#7AA2F7" label={item.label} meta={item.summary} active={active} />
          <SearchHit excerpt={excerpt} marginLeft={4} />
          <ExpandHint expanded={detailsExpanded} />
          {(detailsExpanded ? item.lines : (item.collapsedLines ?? summarizeLines(item.lines))).map((line, index) => (
            <DetailLine key={`${item.id}-${index}`} text={line} dim />
          ))}
          {!detailsExpanded && (item.overflowCount ?? 0) > 0 ? <DetailLine text={`+${item.overflowCount} more`} dim /> : null}
        </Box>
      );
    case 'error':
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1}>
          <ItemHeader marker="!" markerColor="#F07C82" label={item.label} active={active} />
          <SearchHit excerpt={excerpt} marginLeft={4} />
          <DetailLine text="Review the latest failure and retry path." color="#F7C4C7" />
          <DetailLine text={item.text} color="#F07C82" />
        </Box>
      );
    case 'progress':
      return (
        <Box flexDirection="column" marginLeft={2} marginTop={1}>
          <ItemHeader marker="~" markerColor="#DA7756" label={item.label} meta={item.elapsedText} active={active} />
          <SearchHit excerpt={excerpt} marginLeft={4} />
          <ExpandHint expanded={detailsExpanded} />
          {(detailsExpanded ? item.lines : summarizeLines(item.lines)).map((line, index) => (
            <DetailLine key={`${item.id}-${index}`} text={line} dim />
          ))}
        </Box>
      );
    default:
      return null;
  }
}

export function CodexTimeline({
  state,
  search,
  detailsExpanded = false,
}: {
  state: CodexTimelineState;
  search?: CodexTimelineSearchState;
  detailsExpanded?: boolean;
}): React.ReactNode {
  return (
    <Box flexDirection="column">
      {state.blocks.map((block, blockIndex) => {
        if (block.kind === 'user_message') {
          const active = search?.activeDocumentId === block.id;
          return (
            <Box key={block.id} flexDirection="column" marginBottom={1}>
              <Box>
                <Text color={active ? '#7AA2F7' : '#5FA8D3'}>{'>'}</Text>
                <Text color={active ? '#7AA2F7' : '#5FA8D3'} bold>{' You'}</Text>
              </Box>
              <SearchHit excerpt={active ? search.activeExcerpt : null} />
              <Box marginLeft={2}>
                <Markdown>{block.message.text}</Markdown>
              </Box>
            </Box>
          );
        }

        if (block.kind === 'assistant_message') {
          const active = search?.activeDocumentId === block.id;
          return (
            <Box key={block.id} flexDirection="column" marginBottom={1}>
              <Box>
                <Text color={active ? '#7AA2F7' : '#DA7756'}>{active ? '>' : 'o'}</Text>
                <Text color={active ? '#7AA2F7' : '#DA7756'} bold>
                  {block.message.role === 'system' ? ' System' : ' Jarvis'}
                </Text>
              </Box>
              <SearchHit excerpt={active ? search.activeExcerpt : null} />
              <Box marginLeft={2}>
                <Markdown>{block.message.text}</Markdown>
              </Box>
            </Box>
          );
        }

        const turn = block.turn;
        const turnActive = turn.items.some((item) => search?.activeDocumentId === `item:${turn.turnId}:${item.id}`);
        return (
          <Box
            key={block.id}
            flexDirection="column"
            marginBottom={blockIndex === state.blocks.length - 1 ? 0 : 1}
          >
            <TurnHeader turn={turn} active={turnActive} />
            {turn.items.map((item) => {
              const active = search?.activeDocumentId === `item:${turn.turnId}:${item.id}`;
              return (
                <TimelineItemView
                  key={item.id}
                  item={item}
                  active={active}
                  excerpt={active ? search?.activeExcerpt : null}
                  detailsExpanded={detailsExpanded}
                />
              );
            })}
          </Box>
        );
      })}
    </Box>
  );
}
