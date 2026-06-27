import { join, resolve } from "node:path";
import process from "node:process";
import { loadProjectEnv, runReplay, type ReplayAction, type ReplayOptions } from "./replay.js";
import { loadJarvisConfig } from "@jarvis/shared";

function baseReplayOptions(): Omit<ReplayOptions, "prompt" | "snapshotDir"> {
  const userConfig = loadJarvisConfig();
  return {
    model: userConfig.model ?? process.env["JARVIS_LLM_MODEL"] ?? process.env["JARVIS_MODEL"] ?? "deepseek-v4-pro",
    // Let App resolve provider credentials from the selected model, just like
    // the real interactive entrypoint does. Hard-coding replay suite baseURL /
    // apiKey here can force the run onto a stale endpoint and block the real
    // answer-stream scenarios before they start streaming.
    apiKey: undefined,
    baseURL: undefined,
    maxTurns: userConfig.max_turns ?? 30,
    presentationMode: "codex",
    waitMs: 15000,
    inputDelayMs: 300,
    submitCount: 1,
    betweenPromptsMs: 900,
    interruptCount: 0,
    expandDetailsCount: 0,
    searchNextCount: 0,
    width: 120,
    height: 40,
    shellMode: false,
  };
}

function scenarioDir(name: string): string {
  return resolve(process.cwd(), ".jarvis", "debug", "tui-replay", "suite", name);
}

export function buildHistoryDriftDuringToolsScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 2200 },
    { type: "key", key: "pageup", count: 3, delayMs: 120 },
    { type: "wait", ms: 2200 },
    { type: "key", key: "pagedown", count: 1, delayMs: 120 },
    { type: "wait", ms: 1800 },
  ];
}

export function buildHistoryDriftDuringAnswerScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 4400 },
    { type: "key", key: "pageup", count: 4, delayMs: 110 },
    { type: "wait", ms: 1800 },
    { type: "key", key: "pagedown", count: 1, delayMs: 110 },
    { type: "wait", ms: 1400 },
  ];
}

export function buildHistoryDriftDuringLongAnswerTailScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 5200 },
    { type: "key", key: "pageup", count: 4, delayMs: 110 },
    { type: "wait", ms: 3200 },
    { type: "key", key: "pagedown", count: 1, delayMs: 110 },
    { type: "wait", ms: 1800 },
  ];
}

export function buildFinalizeTimeoutPhaseDiagnosticScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 3000 },
  ];
}

export function buildNoProgressPhaseDiagnosticScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 2200 },
  ];
}

export function buildToolHeavyFinalizeTimeoutScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 4200 },
    { type: "wait", ms: 2200 },
  ];
}

export function buildToolHeavyNoProgressScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 3600 },
    { type: "wait", ms: 1800 },
  ];
}

export function buildSelectionDuringToolsScript(): ReplayAction[] {
  return [
    { type: "wait", ms: 2400 },
    { type: "select", start: { col: 2, row: 10 }, end: { col: 72, row: 16 }, delayMs: 180 },
    { type: "wait", ms: 2600 },
  ];
}

export function buildToolHeavyPrompt(): string {
  return [
    "Inspect the Jarvis repository and compare the current TUI/runtime structure.",
    "Use multiple read-only tools while you work: list directories, read key files, and run shell search commands.",
    "Keep working for a bit before summarizing so the transcript gets several tool/progress updates.",
  ].join(" ");
}

export function buildRealToolHeavyPrompt(): string {
  return [
    "Inspect the Jarvis repository and compare the current TUI/runtime structure.",
    "Use multiple read-only tools while you work: list directories, read key files, and run shell search commands.",
    "Do not write files, do not use plan mode, and do not ask follow-up questions.",
    "After a short tool-heavy investigation, give a concise summary in 3 bullet points.",
  ].join(" ");
}

export function buildLongAnswerPrompt(): string {
  return [
    "Write a very long answer about why fullscreen terminal UIs can lose viewport stability during streaming output.",
    "Use multiple sections, concrete examples, and a numbered checklist at the end.",
    "Do not use tools or shell commands.",
    "Keep the answer long enough that it must stream for a while and wrap across many terminal lines.",
  ].join(" ");
}

export function buildToolHeavyFinalizeTimeoutPrompt(): string {
  return [
    "Run a tool-heavy, read-only investigation of the Jarvis TUI/runtime flow.",
    "Use read-only tools and complete the investigation before attempting the final answer.",
    "Keep the tool-heavy work visible so the replay can inspect what happens after tools finish and before the final answer.",
  ].join(" ");
}

export function buildToolHeavyNoProgressPrompt(): string {
  return [
    "Run a tool-heavy, read-only investigation of the Jarvis TUI/runtime flow.",
    "Use read-only tools and keep the investigation visible while the replay diagnoses the stall.",
    "Keep the tool-heavy work visible so the replay can inspect a post-tool stall.",
    "After the read-only investigation, simulate a no-progress stop instead of reaching a final answer.",
  ].join(" ");
}

async function runScenario(
  name: string,
  overrides: Partial<ReplayOptions> & Pick<ReplayOptions, "prompt">,
): Promise<void> {
  const { prompt, ...rest } = overrides;
  const options: ReplayOptions = {
    ...baseReplayOptions(),
    snapshotDir: scenarioDir(name),
    ...rest,
    prompt,
  };
  process.stdout.write(`Running replay scenario: ${name}\n`);
  await runReplay(options);
}

const reinputScript: ReplayAction[] = [
  { type: "text", value: "hello??", delayMs: 25 },
  { type: "key", key: "backspace", count: 2, delayMs: 30 },
  { type: "text", value: "Jarvis", delayMs: 25 },
  { type: "key", key: "enter" },
  { type: "wait", ms: 800 },
  { type: "text", value: "/model", delayMs: 25 },
  { type: "key", key: "enter", count: 2, delayMs: 40 },
];

const SCENARIOS = {
  "multi-turn": async () =>
    runScenario("multi-turn", {
      prompt: "hello",
      prompts: ["hello", "/model", "Summarize the current TUI state in one sentence."],
      waitMs: 18000,
    }),
  reinput: async () =>
    runScenario("reinput", {
      prompt: "hello",
      actionScript: reinputScript,
      waitMs: 12000,
    }),
  "failed-turn": async () =>
    runScenario("failed-turn", {
      prompt: "hello",
      baseURL: "http://127.0.0.1:1",
      waitMs: 6000,
    }),
  interrupt: async () =>
    runScenario("interrupt", {
      prompt: "Write a very detailed numbered checklist with 200 items about improving a terminal UI.",
      waitMs: 12000,
      interruptDelayMs: 1200,
      interruptCount: 1,
    }),
  "history-drift-during-tools": async () =>
    runScenario("history-drift-during-tools", {
      prompt: buildToolHeavyPrompt(),
      fixtureScenario: "tool-heavy-answer",
      actionScript: buildHistoryDriftDuringToolsScript(),
      waitMs: 16000,
      betweenPromptsMs: 1200,
      width: 132,
      height: 42,
    }),
  "selection-during-tools": async () =>
    runScenario("selection-during-tools", {
      prompt: buildToolHeavyPrompt(),
      fixtureScenario: "tool-heavy-answer",
      actionScript: buildSelectionDuringToolsScript(),
      waitMs: 16000,
      betweenPromptsMs: 1200,
      width: 132,
      height: 42,
    }),
  "history-drift-during-answer-stream": async () =>
    runScenario("history-drift-during-answer-stream", {
      prompt: buildToolHeavyPrompt(),
      fixtureScenario: "tool-heavy-answer",
      actionScript: buildHistoryDriftDuringAnswerScript(),
      waitMs: 16000,
      betweenPromptsMs: 1200,
      width: 132,
      height: 42,
    }),
  "history-drift-during-answer-tail-stream": async () =>
    runScenario("history-drift-during-answer-tail-stream", {
      prompt: buildToolHeavyPrompt(),
      fixtureScenario: "tool-heavy-answer-long-tail",
      actionScript: buildHistoryDriftDuringLongAnswerTailScript(),
      waitMs: 18000,
      betweenPromptsMs: 1200,
      width: 132,
      height: 42,
    }),
  "phase-diagnostic-finalize-timeout": async () =>
    runScenario("phase-diagnostic-finalize-timeout", {
      prompt: "Simulate a finalize-timeout diagnostic replay.",
      fixtureScenario: "phase-diagnostic-finalize-timeout",
      actionScript: buildFinalizeTimeoutPhaseDiagnosticScript(),
      waitMs: 6000,
      width: 120,
      height: 36,
    }),
  "phase-diagnostic-no-progress": async () =>
    runScenario("phase-diagnostic-no-progress", {
      prompt: "Simulate a no-progress diagnostic replay.",
      fixtureScenario: "phase-diagnostic-no-progress",
      actionScript: buildNoProgressPhaseDiagnosticScript(),
      waitMs: 5000,
      width: 120,
      height: 36,
    }),
  "tool-heavy-finalize-timeout": async () =>
    runScenario("tool-heavy-finalize-timeout", {
      prompt: buildToolHeavyFinalizeTimeoutPrompt(),
      fixtureScenario: "tool-heavy-finalize-timeout",
      actionScript: buildToolHeavyFinalizeTimeoutScript(),
      waitMs: 9000,
      width: 132,
      height: 42,
    }),
  "tool-heavy-no-progress": async () =>
    runScenario("tool-heavy-no-progress", {
      prompt: buildToolHeavyNoProgressPrompt(),
      fixtureScenario: "tool-heavy-no-progress",
      actionScript: buildToolHeavyNoProgressScript(),
      waitMs: 8000,
      width: 132,
      height: 42,
    }),
  "real-app-tool-heavy-history-drift": async () =>
    runScenario("real-app-tool-heavy-history-drift", {
      prompt: buildRealToolHeavyPrompt(),
      actionScript: buildHistoryDriftDuringToolsScript(),
      waitMs: 14000,
      betweenPromptsMs: 1200,
      interruptDelayMs: 9000,
      interruptCount: 1,
      maxTurns: 8,
      width: 132,
      height: 42,
    }),
  "real-app-answer-stream-history-drift": async () =>
    runScenario("real-app-answer-stream-history-drift", {
      prompt: buildLongAnswerPrompt(),
      actionScript: buildHistoryDriftDuringAnswerScript(),
      waitMs: 18000,
      betweenPromptsMs: 1200,
      interruptDelayMs: 12000,
      interruptCount: 1,
      width: 132,
      height: 42,
    }),
} as const;

export type ReplaySuiteScenarioName = keyof typeof SCENARIOS;

async function main(): Promise<void> {
  loadProjectEnv();
  const requested = process.argv[2] as ReplaySuiteScenarioName | undefined;

  if (requested) {
    const scenario = SCENARIOS[requested];
    if (!scenario) {
      throw new Error(`Unknown replay suite scenario: ${requested}`);
    }
    await scenario();
    return;
  }

  for (const scenario of Object.values(SCENARIOS)) {
    await scenario();
  }
}

const isMain = process.argv[1] && (
  process.argv[1].endsWith("/replay-suite.ts") ||
  process.argv[1].endsWith("/replay-suite.js") ||
  process.argv[1].endsWith("\\replay-suite.ts") ||
  process.argv[1].endsWith("\\replay-suite.js")
);

if (isMain) {
  main().catch((error) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exit(1);
  });
}
