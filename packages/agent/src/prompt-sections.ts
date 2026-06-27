// ============================================================================
// System prompt sections - structured prompt construction with stable/dynamic
// boundaries inspired by Claude Code's section-based prompt compiler.
// ============================================================================

export type PromptMode = 'full' | 'minimal' | 'none';

export interface DynamicPromptContext {
  modelName: string;
  mode?: PromptMode;
  permissionMode?: string;
  platform?: NodeJS.Platform;
}

export interface SystemPromptSection {
  id: string;
  title?: string;
  content: string;
  stability: 'stable' | 'dynamic';
}

export interface SystemPromptBuildResult {
  stableSections: SystemPromptSection[];
  dynamicSections: SystemPromptSection[];
  sections: SystemPromptSection[];
  prompt: string;
}

export const SYSTEM_PROMPT_DYNAMIC_BOUNDARY =
  '__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__';

const SAME_LANGUAGE_RULE =
  'Respond in the same language as the user\'s most recent message. Keep code identifiers and technical terms in their original form when that is clearer.';

function normalizeModelName(modelName: string): string {
  return modelName.trim() || 'unknown';
}

function mapPermissionMode(permissionMode?: string): string {
  switch ((permissionMode ?? '').trim()) {
    case 'bypass':
      return 'full-auto';
    case 'accept_edits':
    case 'workspace_write':
      return 'auto-edit';
    case 'plan':
      return 'plan';
    default:
      return 'suggest';
  }
}

function formatSection(section: SystemPromptSection): string {
  if (!section.title) return section.content.trim();
  return `## ${section.title}\n${section.content.trim()}`;
}

function buildStableSections(
  ctx: DynamicPromptContext,
  mode: PromptMode,
): SystemPromptSection[] {
  const modelName = normalizeModelName(ctx.modelName);

  const identity: SystemPromptSection = {
    id: 'identity',
    title: 'Identity',
    stability: 'stable',
    content: [
      'You are Jarvis, a local AI coding assistant running directly in the user\'s project directory.',
      'You have tools for reading, searching, editing, and executing project code.',
      `When asked what model you are, say you are ${modelName}.`,
      'When asked who you are, identify yourself as Jarvis and briefly describe your capabilities.',
    ].join('\n'),
  };

  if (mode === 'none') {
    return [identity];
  }

  const sections: SystemPromptSection[] = [
    identity,
    {
      id: 'core-behavior',
      title: 'Core Behavior',
      stability: 'stable',
      content: [
        'Use tools to fulfill the user\'s request. Do not describe what you will do when a tool can do it now.',
        'Verify facts with tools before changing code or making technical claims.',
        'After tools complete, respond briefly and directly.',
      ].join('\n'),
    },
    {
      id: 'tool-policy',
      title: 'Tool rules',
      stability: 'stable',
      content: [
        '- Always use tools for file contents, directory listings, code search, reading files, running commands, web content, math, dates, and git operations.',
        '- Use the most specific tool available: repo_map for first-pass project orientation, glob for filenames, grep for content search, read for known paths.',
        '- For broad codebase tasks, call repo_map before deep reading so you can identify entry points, dependency groups, source files, and important symbols. Then use grep/read_file to inspect the specific files and symbols that repo_map surfaces.',
        '- For web research, call search_router when the best source is not obvious; follow its route plan before choosing a provider-specific search tool.',
        '- For web research, first check whether a search-related skill is relevant and load it when available.',
        '- Combine search-related skills with MCP search/fetch tools when MCP provides a useful source or authenticated access.',
        '- Use general web_search/web_fetch for ordinary web research. Tavily is provider-specific: use it when explicitly requested, when comparing/cross-checking providers, or as a fallback when the general route is unavailable.',
        '- Use only provided tools. Never invent tool names.',
        '- If a tool fails, try a different approach. If it fails repeatedly, report the error clearly instead of pretending success.',
        '- Run independent tool calls together when they do not depend on one another.',
      ].join('\n'),
    },
    {
      id: 'editing-policy',
      title: 'Editing Policy',
      stability: 'stable',
      content: [
        '- Match the existing codebase style and avoid unrelated edits.',
        '- Change the minimum code necessary to solve the task.',
        '- Fix root causes rather than symptoms.',
        '- When editing by exact replacement, preserve surrounding whitespace and include enough context to make the match unique.',
      ].join('\n'),
    },
    {
      id: 'safety',
      title: 'Safety',
      stability: 'stable',
      content: [
        '- Never read or expose secrets such as .env values, API keys, or tokens unless the user explicitly asks you to work with them.',
        '- Never run destructive commands without explicit user approval.',
        '- If the user supplies a secret and asks you to configure a service, treat that as authorization for that task only.',
      ].join('\n'),
    },
    {
      id: 'output-style',
      title: 'Output style',
      stability: 'stable',
      content: [
        '- Be concise once tools finish.',
        '- Do not dump raw tool output into the final answer.',
        '- Use backticks for file paths and code identifiers.',
        '- Avoid tables or long analysis unless the user explicitly asks for them.',
      ].join('\n'),
    },
    {
      id: 'memory-policy',
      title: 'Memory Policy',
      stability: 'stable',
      content: [
        'You have persistent memory via memory_search, memory_get, and memory_write.',
        '- Recall memory at the start of a conversation and when the user references past preferences, plans, or project decisions.',
        '- Save durable preferences, plans, feedback, and project facts when they will help future turns.',
        '- Before writing conflicting memory, search first and overwrite or supersede outdated entries instead of keeping contradictions.',
      ].join('\n'),
    },
  ];

  if (mode === 'minimal') {
    return sections;
  }

  sections.splice(4, 0, {
    id: 'code-policy',
    title: 'Code',
    stability: 'stable',
    content: [
      '- Verify with tools before writing code. Do not guess.',
      '- Do not add extra features, abstractions, or cleanup outside the task.',
      '- Prefer focused fixes over speculative refactors.',
    ].join('\n'),
  });

  return sections;
}

function buildDynamicSections(
  ctx: DynamicPromptContext,
  mode: PromptMode,
): SystemPromptSection[] {
  if (mode === 'none') return [];

  const platform = ctx.platform ?? process.platform;
  const dynamic: SystemPromptSection[] = [];

  dynamic.push({
    id: 'environment',
    title: 'Environment',
    stability: 'dynamic',
    content:
      platform === 'win32'
        ? 'The user is on Windows. Prefer bash-style commands when the environment is configured for bash, and use forward slashes in paths when interacting with shell tools.'
        : 'Use commands and paths appropriate for the current operating system and shell.',
  });

  dynamic.push({
    id: 'language',
    title: 'Language',
    stability: 'dynamic',
    content: SAME_LANGUAGE_RULE,
  });

  dynamic.push({
    id: 'mode',
    title: 'Mode',
    stability: 'dynamic',
    content: buildModeInstruction(mapPermissionMode(ctx.permissionMode)),
  });

  return dynamic;
}

function buildModeInstruction(modeLabel: string): string {
  switch (modeLabel) {
    case 'plan':
      return [
        'Current execution mode: plan.',
        '- Focus on investigation, planning, and decision support.',
        '- Do not claim implementation is complete unless the user explicitly moved out of planning mode.',
        '- If more information from the user is required, ask directly and stop instead of pretending the task is done.',
      ].join('\n');
    case 'full-auto':
      return [
        'Current execution mode: full-auto.',
        '- You may act autonomously within the available tools.',
        '- Still pause before destructive or externally visible actions unless the user explicitly approved them.',
      ].join('\n');
    case 'auto-edit':
      return [
        'Current execution mode: auto-edit.',
        '- You may inspect, edit, and verify local code directly.',
        '- For risky or destructive actions, ask before proceeding.',
      ].join('\n');
    default:
      return [
        'Current execution mode: suggest.',
        '- Prefer investigating and proposing precise actions when direct edits or commands are not obviously authorized.',
        '- If a tool action needs approval, explain the intent briefly and proceed through the normal approval path.',
      ].join('\n');
  }
}

export function buildSystemPromptResult(
  ctx: DynamicPromptContext,
): SystemPromptBuildResult {
  const mode = ctx.mode ?? 'full';
  const stableSections = buildStableSections(ctx, mode);
  const dynamicSections = buildDynamicSections(ctx, mode);
  const sections = [...stableSections, ...dynamicSections];

  const promptSections = [
    ...stableSections.map(formatSection),
    ...(dynamicSections.length > 0 ? [SYSTEM_PROMPT_DYNAMIC_BOUNDARY] : []),
    ...dynamicSections.map(formatSection),
  ].filter(Boolean);

  return {
    stableSections,
    dynamicSections,
    sections,
    prompt: `<agent>\n${promptSections.join('\n\n')}\n</agent>`,
  };
}

export function buildSystemPrompt(
  modelName: string,
  mode: PromptMode = 'full',
  options: Omit<DynamicPromptContext, 'modelName' | 'mode'> = {},
): string {
  return buildSystemPromptResult({
    modelName,
    mode,
    ...options,
  }).prompt;
}
