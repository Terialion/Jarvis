import type {
  ReviewDecision,
  ReviewFinding,
  StructuredSubagentPayload,
  SubagentConfig,
  SubagentResult,
} from './models.js';

type ParsedStructuredResult = {
  summary?: string;
  artifacts?: Array<{ kind?: string; label?: string; path?: string; detail?: string }>;
  evidence?: Array<{ kind?: string; summary?: string; source?: string }>;
  risks?: Array<{ severity?: string; summary?: string }>;
  nextActions?: string[];
  confidence?: number;
  facts?: string[];
  files?: string[];
  openQuestions?: string[];
  tasks?: string[];
  dependencies?: string[];
  assumptions?: string[];
  changedFiles?: string[];
  commandsRun?: string[];
  verification?: string[];
  findings?: Array<{ severity?: string; summary?: string; detail?: string; file?: string }>;
  decision?: string;
};

function clampConfidence(value: unknown): number {
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return 0.5;
  return Math.max(0, Math.min(1, numeric));
}

function normalizeDecision(value: unknown): ReviewDecision | undefined {
  if (typeof value !== 'string') return undefined;
  const normalized = value.trim().toLowerCase();
  if (normalized === 'pass' || normalized === 'needs_fix' || normalized === 'blocked') {
    return normalized;
  }
  return undefined;
}

function normalizeSeverity(value: unknown): 'low' | 'medium' | 'high' {
  const normalized = typeof value === 'string' ? value.trim().toLowerCase() : '';
  if (normalized === 'low' || normalized === 'high') return normalized;
  return 'medium';
}

function extractJsonCandidate(rawAnswer: string): string | null {
  const fenced = rawAnswer.match(/```json\s*([\s\S]*?)```/i);
  if (fenced?.[1]) return fenced[1].trim();
  const tagged = rawAnswer.match(/<subagent-result>\s*([\s\S]*?)<\/subagent-result>/i);
  if (tagged?.[1]) return tagged[1].trim();
  const trimmed = rawAnswer.trim();
  if (trimmed.startsWith('{') && trimmed.endsWith('}')) return trimmed;
  return null;
}

function parseStructuredResult(rawAnswer: string): ParsedStructuredResult | null {
  const candidate = extractJsonCandidate(rawAnswer);
  if (!candidate) return null;
  try {
    return JSON.parse(candidate) as ParsedStructuredResult;
  } catch {
    return null;
  }
}

function inferKind(agentType: string): StructuredSubagentPayload['kind'] {
  switch (agentType) {
    case 'explore':
      return 'explore';
    case 'plan':
      return 'plan';
    case 'review':
      return 'review';
    case 'general':
      return 'implement';
    default:
      return 'general';
  }
}

function fallbackSummary(rawAnswer: string, error?: string): string {
  const text = (rawAnswer || error || '').trim();
  if (!text) return error ? `Failed: ${error}` : 'No summary provided.';
  const firstParagraph = text.split(/\n\s*\n/).find((part) => part.trim()) ?? text;
  return firstParagraph.replace(/\s+/g, ' ').trim().slice(0, 240) || 'No summary provided.';
}

function extractLikelyFiles(rawAnswer: string): string[] {
  return [...new Set(
    [...rawAnswer.matchAll(/[A-Za-z]:\\[^\s"'`]+|(?:[\w.-]+\/)+[\w.-]+/g)]
      .map((match) => match[0])
      .filter((value) => /\.[A-Za-z0-9]{1,8}$/.test(value)),
  )];
}

function normalizeFindings(findings: ParsedStructuredResult['findings']): ReviewFinding[] {
  return (findings ?? [])
    .filter((finding) => typeof finding?.summary === 'string' && finding.summary.trim().length > 0)
    .map((finding) => ({
      severity: normalizeSeverity(finding?.severity),
      summary: String(finding?.summary ?? '').trim(),
      detail: typeof finding?.detail === 'string' ? finding.detail.trim() : undefined,
      file: typeof finding?.file === 'string' ? finding.file.trim() : undefined,
    }));
}

export function buildStructuredPayload(
  config: Pick<SubagentConfig, 'agentType' | 'expectedOutput' | 'successCriteria'>,
  rawAnswer: string,
  error?: string,
): StructuredSubagentPayload {
  const parsed = parseStructuredResult(rawAnswer);
  const findings = normalizeFindings(parsed?.findings);
  const inferredFiles = extractLikelyFiles(rawAnswer);
  const decision = normalizeDecision(parsed?.decision);

  return {
    kind: inferKind(config.agentType),
    summary: (parsed?.summary && parsed.summary.trim()) || fallbackSummary(rawAnswer, error),
    artifacts: (parsed?.artifacts ?? [])
      .filter((item) => typeof item?.label === 'string' && item.label.trim().length > 0)
      .map((item) => ({
        kind: typeof item?.kind === 'string' ? item.kind.trim() : 'artifact',
        label: String(item?.label ?? '').trim(),
        path: typeof item?.path === 'string' ? item.path.trim() : undefined,
        detail: typeof item?.detail === 'string' ? item.detail.trim() : undefined,
      })),
    evidence: (parsed?.evidence ?? [])
      .filter((item) => typeof item?.summary === 'string' && item.summary.trim().length > 0)
      .map((item) => ({
        kind: typeof item?.kind === 'string' ? item.kind.trim() : 'evidence',
        summary: String(item?.summary ?? '').trim(),
        source: typeof item?.source === 'string' ? item.source.trim() : undefined,
      })),
    risks: (parsed?.risks ?? [])
      .filter((item) => typeof item?.summary === 'string' && item.summary.trim().length > 0)
      .map((item) => ({
        severity: normalizeSeverity(item?.severity),
        summary: String(item?.summary ?? '').trim(),
      })),
    nextActions: (parsed?.nextActions ?? []).filter((item): item is string => typeof item === 'string' && item.trim().length > 0),
    confidence: clampConfidence(parsed?.confidence),
    rawAnswer,
    facts: parsed?.facts ?? [],
    files: parsed?.files?.length ? parsed.files : inferredFiles,
    openQuestions: parsed?.openQuestions ?? [],
    tasks: parsed?.tasks ?? [],
    dependencies: parsed?.dependencies ?? [],
    assumptions: parsed?.assumptions ?? [],
    changedFiles: parsed?.changedFiles ?? inferredFiles,
    commandsRun: parsed?.commandsRun ?? [],
    verification: parsed?.verification ?? [],
    findings,
    decision,
  };
}

export function mergeReviewIntoResult(
  base: SubagentResult,
  reviewPayload: StructuredSubagentPayload,
): SubagentResult {
  return {
    ...base,
    reviewStatus: reviewPayload.decision ?? (reviewPayload.findings && reviewPayload.findings.length > 0 ? 'needs_fix' : 'pass'),
    reviewResult: reviewPayload,
  };
}

export function buildReviewerTask(config: SubagentConfig, workerResult: SubagentResult): string {
  const summary = workerResult.payload?.summary ?? workerResult.answer ?? workerResult.error ?? '(no output)';
  const verification = workerResult.payload?.verification?.join('\n- ') ?? '';
  const changedFiles = workerResult.payload?.changedFiles?.join('\n- ') ?? '';
  const criteria = config.successCriteria?.trim() ? `Success criteria:\n${config.successCriteria.trim()}\n\n` : '';
  const expected = config.expectedOutput?.trim() ? `Expected output:\n${config.expectedOutput.trim()}\n\n` : '';

  return [
    'Review the worker result below and decide whether it meets the task goal.',
    'Return a structured result in JSON inside ```json fences with:',
    '{ "summary": string, "decision": "pass|needs_fix|blocked", "findings": [{ "severity": "low|medium|high", "summary": string, "detail"?: string, "file"?: string }], "nextActions": string[], "confidence": number }',
    '',
    criteria + expected,
    `Original task:\n${config.task}`,
    '',
    `Worker summary:\n${summary}`,
    changedFiles ? `\nChanged files:\n- ${changedFiles}` : '',
    verification ? `\nVerification notes:\n- ${verification}` : '',
    '',
    'Mark "pass" only if the result is sufficient to merge back to the parent agent.',
  ].filter(Boolean).join('\n');
}
