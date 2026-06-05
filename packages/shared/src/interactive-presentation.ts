import { relative } from 'node:path';

export type ToolCardView = {
  label: string;
  status: string;
  statusLabel: string;
  summary?: string;
  collapsedDetail?: string;
  argumentsText?: string;
  resultText?: string;
  errorText?: string;
  mcpSource?: string;
  failureReason?: string;
  previewLines?: string[];
  previewOverflowCount?: number;
  alwaysShowPreview?: boolean;
  previewKind?: 'code' | 'diff';
};

export type PresentationTextColor = 'cyan' | 'green' | 'yellow' | 'red' | 'gray' | 'white' | 'blue';

export type PresentationTextSegment = {
  content: string;
  color?: PresentationTextColor;
  bold?: boolean;
  dim?: boolean;
};

export type PresentationTextLine = PresentationTextSegment[];

export type ThoughtBlockView = {
  label: string;
  meta?: string;
  text: string;
};

export type PlanBlockView = {
  title: string;
  lines: string[];
};

export type PresentationItem =
  | ({ kind: 'tool_call' } & ToolCardView)
  | ({ kind: 'thought' } & ThoughtBlockView)
  | ({ kind: 'plan' } & PlanBlockView)
  | { kind: 'text'; text: string };

export type PresentationTurn = {
  turnId: string;
  turnNumber?: number;
  status: 'running' | 'completed' | 'failed';
  statusText: string;
  statsText?: string;
  items: PresentationItem[];
};

export type SlashResultBlock =
  | {
      kind: 'text';
      text: string;
    }
  | {
      kind: 'section';
      title: string;
      lines: string[];
    }
  | {
      kind: 'list';
      title?: string;
      ordered?: boolean;
      items: string[];
    }
  | {
      kind: 'table';
      title?: string;
      headers: string[];
      rows: string[][];
    }
  | {
      kind: 'status_summary';
      title: string;
      lines: string[];
    };

export type SlashResult = string | SlashResultBlock[];

function truncate(text: string, limit = 280): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}...`;
}

function normalizeText(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

function getPathLabel(pathValue: unknown, cwd = process.cwd()): string | undefined {
  if (typeof pathValue !== 'string' || !pathValue.trim()) return undefined;
  const normalized = pathValue.trim().replace(/\//g, '\\');
  const normalizedCwd = cwd.replace(/\//g, '\\');
  if (normalized.toLowerCase().startsWith(normalizedCwd.toLowerCase())) {
    const rel = relative(normalizedCwd, normalized).replace(/\//g, '\\');
    return rel || normalized;
  }
  return normalized;
}

function getLineArray(text: string): string[] {
  return text.replace(/\r/g, '').split('\n');
}

function countLines(text: string): number {
  if (!text) return 0;
  return getLineArray(text).length;
}

function parseJsonObject(text?: string): Record<string, unknown> | null {
  if (!text) return null;
  try {
    const parsed = JSON.parse(text) as unknown;
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? (parsed as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function wasOverwriteWrite(resultText?: string): boolean {
  const parsed = parseJsonObject(resultText);
  return parsed?.existedBefore === true;
}

function parseMcpToolName(toolName: string): { server: string; tool: string } | null {
  if (!toolName.startsWith('mcp__')) return null;
  const parts = toolName.split('__');
  if (parts.length < 3) return null;
  return {
    server: parts[1] || 'unknown',
    tool: parts.slice(2).join('__') || 'tool',
  };
}

function buildToolTitle(
  toolName: string,
  args: Record<string, unknown>,
  resultText?: string,
  cwd = process.cwd(),
): string {
  const mcpMeta = parseMcpToolName(toolName);
  if (mcpMeta) {
    return `MCP(${mcpMeta.server}/${mcpMeta.tool})`;
  }
  switch (toolName) {
    case 'bash': {
      const command = typeof args.command === 'string' ? normalizeText(args.command) : '';
      return command ? `Bash(${truncate(command, 56)})` : 'Bash';
    }
    case 'write_file':
    case 'write': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      return pathLabel ? `Write(${pathLabel})` : 'Write';
    }
    case 'edit_file':
    case 'edit': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      return pathLabel ? `Update(${pathLabel})` : 'Update';
    }
    case 'read_file':
    case 'read': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      return pathLabel ? `Read(${pathLabel})` : 'Read';
    }
    case 'glob': {
      const pattern = typeof args.pattern === 'string' ? normalizeText(args.pattern) : '';
      return pattern ? `Glob(${truncate(pattern, 40)})` : 'Glob';
    }
    case 'grep': {
      const pattern = typeof args.pattern === 'string' ? normalizeText(args.pattern) : '';
      return pattern ? `Grep(${truncate(pattern, 36)})` : 'Grep';
    }
    case 'skill.load': {
      const skill = typeof args.skill === 'string' ? normalizeText(args.skill) : '';
      return skill ? `Skill(${skill})` : 'Skill';
    }
    default:
      return humanizeToolName(toolName);
  }
}

function humanizeToolName(toolName: string): string {
  const normalized = toolName.replace(/\./g, '_');
  return normalized
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function buildToolResultSummary(
  toolName: string,
  args: Record<string, unknown>,
  resultText?: string,
  cwd = process.cwd(),
): string | undefined {
  const parsed = parseJsonObject(resultText);
  switch (toolName) {
    case 'write_file':
    case 'write': {
      const content = typeof args.content === 'string' ? args.content : '';
      const lineCount = countLines(content);
      const unit = lineCount === 1 ? 'line' : 'lines';
      if (lineCount > 0 && wasOverwriteWrite(resultText)) return `Replaced ${lineCount} ${unit}`;
      if (lineCount > 0) return `Added ${lineCount} ${unit}`;
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      return pathLabel ? `Wrote file ${pathLabel}` : 'Wrote file';
    }
    case 'edit_file':
    case 'edit': {
      const oldString = typeof args.old_string === 'string' ? args.old_string : '';
      const newString = typeof args.new_string === 'string' ? args.new_string : '';
      const removedLines = countLines(oldString);
      const addedLines = countLines(newString);
      const replacements = parsed && typeof parsed.replacements === 'number' ? parsed.replacements : undefined;
      if (addedLines > 0 || removedLines > 0) {
        const addUnit = addedLines === 1 ? 'line' : 'lines';
        const remUnit = removedLines === 1 ? 'line' : 'lines';
        return `Added ${addedLines} ${addUnit}, removed ${removedLines} ${remUnit}`;
      }
      if (replacements) return `${replacements} replacements`;
      return 'Updated';
    }
    case 'read_file':
    case 'read': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      if (pathLabel) return `Read ${pathLabel}`;
      break;
    }
  }

  if (parsed?.ok === true && typeof parsed.path === 'string') {
    return `Updated ${getPathLabel(parsed.path, cwd) ?? parsed.path}`;
  }
  return undefined;
}

function buildToolArgumentsSummary(
  toolName: string,
  args: Record<string, unknown>,
  cwd = process.cwd(),
): string | undefined {
  switch (toolName) {
    case 'bash': {
      const command = typeof args.command === 'string' ? normalizeText(args.command) : '';
      return command ? truncate(command, 180) : undefined;
    }
    case 'write_file':
    case 'write': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      const content = typeof args.content === 'string' ? args.content : '';
      const lineCount = countLines(content);
      return pathLabel ? `${pathLabel} | ${lineCount} lines` : undefined;
    }
    case 'edit_file':
    case 'edit': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      const oldString = typeof args.old_string === 'string' ? args.old_string : '';
      const newString = typeof args.new_string === 'string' ? args.new_string : '';
      if (!pathLabel) return undefined;
      return `${pathLabel} | -${countLines(oldString)} +${countLines(newString)}`;
    }
    case 'read_file':
    case 'read': {
      const pathLabel = getPathLabel(args.path ?? args.file_path, cwd);
      const limit = typeof args.limit === 'number' ? args.limit : undefined;
      return pathLabel ? `${pathLabel}${limit ? ` | first ${limit} lines` : ''}` : undefined;
    }
    default: {
      const argText = JSON.stringify(args, null, 2);
      return argText !== '{}' ? truncate(argText, 220) : undefined;
    }
  }
}

function buildToolCollapsedDetail(
  toolName: string,
  summary?: string,
  resultText?: string,
  errorText?: string,
): string | undefined {
  if (errorText) return `failed | ${truncate(errorText, 140)}`;
  if (toolName === 'write_file' || toolName === 'write' || toolName === 'edit_file' || toolName === 'edit') {
    return summary ?? (resultText ? truncate(resultText, 140) : undefined);
  }
  if (summary) return summary;
  if (resultText) return `done | ${truncate(resultText, 140)}`;
  return undefined;
}

function buildPreviewLines(lines: string[], limit = 10): { previewLines?: string[]; previewOverflowCount?: number } {
  const normalized = lines
    .map((line) => line.replace(/\t/g, '  '))
    .filter((line, index, array) => !(index === array.length - 1 && line === ''));
  if (normalized.length === 0) return {};
  return {
    previewLines: normalized.slice(0, limit),
    previewOverflowCount: Math.max(0, normalized.length - limit),
  };
}

function buildToolPreview(toolName: string, args: Record<string, unknown>, resultText?: string): Pick<ToolCardView, 'previewLines' | 'previewOverflowCount' | 'alwaysShowPreview' | 'previewKind'> {
  if ((toolName === 'write_file' || toolName === 'write') && typeof args.content === 'string') {
    return { ...buildPreviewLines(getLineArray(args.content), 10), alwaysShowPreview: true, previewKind: 'code' };
  }

  if (toolName === 'edit_file' || toolName === 'edit') {
    const oldString = typeof args.old_string === 'string' ? args.old_string : '';
    const newString = typeof args.new_string === 'string' ? args.new_string : '';
    const parsed = parseJsonObject(resultText);
    const startLine = parsed && typeof parsed.line === 'number' ? parsed.line : 1;
    const contextBefore: string[] = Array.isArray(parsed?.contextBefore) ? (parsed.contextBefore as string[]) : [];
    const contextAfter: string[] = Array.isArray(parsed?.contextAfter) ? (parsed.contextAfter as string[]) : [];
    const oldLines = getLineArray(oldString).filter((line) => line !== '');
    const newLines = getLineArray(newString).filter((line) => line !== '');
    const preview: string[] = [];
    let lineNum = startLine - contextBefore.length;
    for (const line of contextBefore) {
      preview.push(`${String(lineNum).padStart(6)}    ${line}`);
      lineNum += 1;
    }
    const changeRows = Math.min(10, Math.max(oldLines.length, newLines.length));
    for (let i = 0; i < changeRows; i += 1) {
      const currentLineNum = startLine + i;
      const oldLine = oldLines[i];
      const newLine = newLines[i];
      if (typeof oldLine === 'string') {
        preview.push(`${String(currentLineNum).padStart(6)}  - ${oldLine}`);
      }
      if (typeof newLine === 'string') {
        preview.push(`${String(currentLineNum).padStart(6)}  + ${newLine}`);
      }
    }
    const oldCount = parsed && typeof parsed.oldLineCount === 'number' ? parsed.oldLineCount : oldLines.length;
    lineNum = startLine + oldCount;
    for (const line of contextAfter) {
      preview.push(`${String(lineNum).padStart(6)}    ${line}`);
      lineNum += 1;
    }
    return { ...buildPreviewLines(preview, 15), alwaysShowPreview: true, previewKind: 'diff' };
  }

  return {};
}

function formatToolStatus(status: string): string {
  switch (status) {
    case 'completed':
      return 'done';
    case 'failed':
      return 'failed';
    case 'running':
      return 'in_progress';
    default:
      return status;
  }
}

export function buildToolCardView(input: {
  toolName: string;
  args: Record<string, unknown>;
  resultText?: string;
  status?: string;
  errorText?: string;
  cwd?: string;
}): ToolCardView {
  const { toolName, args, resultText, status = 'completed', errorText, cwd = process.cwd() } = input;
  const summary = buildToolResultSummary(toolName, args, resultText, cwd);
  const preview = buildToolPreview(toolName, args, resultText);
  const mcpMeta = parseMcpToolName(toolName);
  return {
    label: buildToolTitle(toolName, args, resultText, cwd),
    status,
    statusLabel: formatToolStatus(status),
    summary,
    collapsedDetail: buildToolCollapsedDetail(toolName, summary, resultText ? truncate(resultText, 260) : undefined, errorText ? truncate(errorText, 260) : undefined),
    argumentsText: buildToolArgumentsSummary(toolName, args, cwd),
    resultText: summary ?? (resultText ? truncate(resultText, 260) : undefined),
    errorText: errorText ? truncate(errorText, 260) : undefined,
    mcpSource: mcpMeta ? mcpMeta.server : undefined,
    failureReason: status === 'failed' ? (errorText ? truncate(errorText, 180) : 'tool failed') : undefined,
    previewLines: preview.previewLines,
    previewOverflowCount: preview.previewOverflowCount,
    alwaysShowPreview: preview.alwaysShowPreview,
    previewKind: preview.previewKind,
  };
}

export function buildInlinePlanReviewText(plan: {
  summary: string;
  steps: Array<{ step: string; files?: string[]; verification?: string }>;
  allowedPrompts?: Array<{ tool: string; prompt: string }>;
}): string {
  const lines = [
    `Updated plan: ${plan.summary}`,
    '',
    ...plan.steps.map((step, index) => {
      const details = [
        step.files?.length ? `[${step.files.join(', ')}]` : '',
        step.verification ? `verify: ${step.verification}` : '',
      ]
        .filter(Boolean)
        .join(' | ');
      return `${index + 1}. ${step.step}${details ? ` | ${details}` : ''}`;
    }),
  ];

  if (plan.allowedPrompts?.length) {
    lines.push('', 'Required permissions:');
    for (const prompt of plan.allowedPrompts) {
      lines.push(`- ${prompt.tool}: ${prompt.prompt}`);
    }
  }

  lines.push('', 'Tell me what to change if this plan needs edits.', 'Otherwise use Enter to proceed or Esc to cancel.');
  return lines.join('\n');
}

export function buildPlanTaskSummaryLines(plan: {
  summary: string;
  steps: Array<{ step: string; files?: string[]; verification?: string }>;
  allowedPrompts?: Array<{ tool: string; prompt: string }>;
}): string[] {
  const lines = [
    `Task summary: ${plan.summary}`,
    `${plan.steps.length} step${plan.steps.length === 1 ? '' : 's'}`,
    ...plan.steps.map((step, index) => {
      const meta = [
        step.files?.length ? `${step.files.length} file${step.files.length === 1 ? '' : 's'}` : '',
        step.verification ? 'has verification' : '',
      ]
        .filter(Boolean)
        .join(' | ');
      return `${index + 1}. ${step.step}${meta ? ` | ${meta}` : ''}`;
    }),
  ];

  if (plan.allowedPrompts?.length) {
    lines.push('Required permissions:');
    for (const prompt of plan.allowedPrompts) {
      lines.push(`- ${prompt.tool}: ${prompt.prompt}`);
    }
  }

  lines.push('Review: [Enter] proceed | [e] edit | [c] cancel');
  return lines;
}

function renderTable(headers: string[], rows: string[][]): string[] {
  const widths = headers.map((header, columnIndex) =>
    Math.max(
      header.length,
      ...rows.map((row) => (row[columnIndex] ?? '').length),
    ),
  );
  const formatRow = (row: string[]) =>
    row.map((cell, index) => (cell ?? '').padEnd(widths[index] ?? 0)).join(' | ').trimEnd();
  const separator = widths.map((width) => '-'.repeat(width)).join(' | ');
  return [formatRow(headers), separator, ...rows.map(formatRow)];
}

export function renderSlashResultText(result: SlashResult): string {
  if (typeof result === 'string') return result;
  const lines: string[] = [];
  for (const block of result) {
    if (lines.length > 0) lines.push('');
    switch (block.kind) {
      case 'text':
        lines.push(block.text);
        break;
      case 'section':
      case 'status_summary':
        lines.push(block.title, ...block.lines);
        break;
      case 'list':
        if (block.title) lines.push(block.title);
        lines.push(
          ...block.items.map((item, index) =>
            block.ordered ? `${index + 1}. ${item}` : `- ${item}`,
          ),
        );
        break;
      case 'table':
        if (block.title) lines.push(block.title);
        lines.push(...renderTable(block.headers, block.rows));
        break;
    }
  }
  return lines.join('\n');
}
