import { join, resolve } from "node:path";
import process from "node:process";
import { loadProjectEnv, runReplay, type ReplayAction, type ReplayOptions } from "./replay.js";

function baseReplayOptions(): Omit<ReplayOptions, "prompt" | "snapshotDir"> {
  return {
    model: process.env["JARVIS_LLM_MODEL"] ?? process.env["JARVIS_MODEL"] ?? "deepseek-v4-pro",
    apiKey: process.env["JARVIS_LLM_API_KEY"] ?? process.env["OPENAI_API_KEY"],
    baseURL: process.env["JARVIS_LLM_BASE_URL"] ?? process.env["JARVIS_BASE_URL"] ?? "https://api.deepseek.com/v1",
    maxTurns: 30,
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
  };
}

function scenarioDir(name: string): string {
  return resolve(process.cwd(), ".jarvis", "debug", "tui-replay", "suite", name);
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

async function main(): Promise<void> {
  loadProjectEnv();

  await runScenario("multi-turn", {
    prompt: "hello",
    prompts: ["hello", "/model", "Summarize the current TUI state in one sentence."],
    waitMs: 18000,
  });

  await runScenario("reinput", {
    prompt: "hello",
    actionScript: reinputScript,
    waitMs: 12000,
  });

  await runScenario("failed-turn", {
    prompt: "hello",
    baseURL: "http://127.0.0.1:1",
    waitMs: 6000,
  });

  await runScenario("interrupt", {
    prompt: "Write a very detailed numbered checklist with 200 items about improving a terminal UI.",
    waitMs: 12000,
    interruptDelayMs: 1200,
    interruptCount: 1,
  });
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
