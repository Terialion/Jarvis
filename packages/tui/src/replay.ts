import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { basename, dirname, join, parse, resolve } from "node:path";
import process from "node:process";
import { PassThrough, Writable } from "node:stream";
import { parseArgs } from "node:util";
import React from "react";
import stripAnsi from "strip-ansi";
import { App } from "./app.js";
import type { TUIDebugEvent, TUIOptions } from "./types.js";
import { createRoot, type RenderOptions } from "./vendor/ink-renderer/root.js";

export type ReplayAction =
  | { type: "text"; value: string; delayMs?: number }
  | { type: "wait"; ms: number }
  | { type: "key"; key: "enter" | "escape" | "backspace" | "ctrl+o" | "ctrl+f"; count?: number; delayMs?: number };

type ReplayKeyAction = Extract<ReplayAction, { type: "key" }>;

export type ReplayOptions = TUIOptions & {
  prompt: string;
  prompts?: string[];
  actionScript?: ReplayAction[];
  waitMs: number;
  inputDelayMs: number;
  submitCount: number;
  betweenPromptsMs: number;
  interruptDelayMs?: number;
  interruptCount: number;
  expandDetailsDelayMs?: number;
  expandDetailsCount: number;
  searchQuery?: string;
  searchDelayMs?: number;
  searchNextCount: number;
  snapshotDir: string;
  width: number;
  height: number;
};

function loadEnvFile(filePath: string): void {
  if (!existsSync(filePath)) return;

  const raw = readFileSync(filePath, "utf8");
  const lines = raw.replace(/\r/g, "").split("\n");

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const eqIndex = trimmed.indexOf("=");
    if (eqIndex === -1) continue;

    const key = trimmed.slice(0, eqIndex).trim();
    const value = trimmed.slice(eqIndex + 1).trim();
    if (key && !(key in process.env)) {
      process.env[key] = value;
    }
  }
}

function findProjectRoot(startDir = process.cwd()): string {
  let dir = resolve(startDir);
  for (let i = 0; i < 10; i += 1) {
    if (basename(dir) === "Jarvis" || dir === parse(dir).root) {
      return dir;
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return resolve(startDir);
}

export function loadProjectEnv(): void {
  loadEnvFile(join(findProjectRoot(), ".env"));
}

type FrameSnapshot = {
  index: number;
  elapsedMs: number;
  ansi: string;
  text: string;
};

class FakeTTYInput extends PassThrough {
  public readonly isTTY = true;
  public isRaw = false;

  override setEncoding(encoding: BufferEncoding): this {
    super.setEncoding(encoding);
    return this;
  }

  setRawMode(isEnabled: boolean): this {
    this.isRaw = isEnabled;
    return this;
  }

  ref(): this {
    return this;
  }

  unref(): this {
    return this;
  }

  send(input: string): void {
    this.write(input);
    this.emit("readable");
  }
}

class RecordingOutput extends Writable {
  public readonly isTTY = false;
  public columns: number;
  public rows: number;
  private frameBuffer = "";
  private transcript = "";

  constructor(columns: number, rows: number) {
    super();
    this.columns = columns;
    this.rows = rows;
  }

  override _write(
    chunk: string | Buffer,
    _encoding: BufferEncoding,
    callback: (error?: Error | null) => void,
  ): void {
    const text = typeof chunk === "string" ? chunk : chunk.toString("utf8");
    this.frameBuffer += text;
    this.transcript += text;
    callback();
  }

  takeFrameChunk(): string {
    const chunk = this.frameBuffer;
    this.frameBuffer = "";
    return chunk;
  }

  getTranscript(): string {
    return this.transcript;
  }
}

function parseReplayArgs(argv: string[] = process.argv): ReplayOptions {
  const { values } = parseArgs({
    args: argv.slice(2),
    options: {
      prompt: { type: "string", default: "/model" },
      "prompt-b64": { type: "string" },
      "prompts-b64": { type: "string" },
      "action-script-b64": { type: "string" },
      model: {
        type: "string",
        default: process.env["JARVIS_LLM_MODEL"] ?? process.env["JARVIS_MODEL"] ?? "deepseek-v4-flash-ascend",
      },
      "api-key": {
        type: "string",
        default: process.env["JARVIS_LLM_API_KEY"] ?? process.env["OPENAI_API_KEY"],
      },
      "base-url": {
        type: "string",
        default: process.env["JARVIS_LLM_BASE_URL"] ?? process.env["JARVIS_BASE_URL"] ?? "https://api.deepseek.com/v1",
      },
      "max-turns": { type: "string", default: "30" },
      "system-prompt": { type: "string" },
      "wait-ms": { type: "string", default: "12000" },
      "input-delay-ms": { type: "string", default: "300" },
      "submit-count": { type: "string" },
      "between-prompts-ms": { type: "string", default: "1200" },
      "interrupt-delay-ms": { type: "string" },
      "interrupt-count": { type: "string", default: "0" },
      "expand-details-delay-ms": { type: "string" },
      "expand-details-count": { type: "string", default: "0" },
      "search-query": { type: "string" },
      "search-delay-ms": { type: "string" },
      "search-next-count": { type: "string", default: "0" },
      "snapshot-dir": { type: "string" },
      width: { type: "string", default: "120" },
      height: { type: "string", default: "40" },
    },
    allowPositionals: false,
  });

  const snapshotDir =
    (values["snapshot-dir"] as string | undefined) ??
    join(process.cwd(), ".jarvis", "debug", "tui-replay", new Date().toISOString().replace(/[:.]/g, "-"));

  const prompt = values["prompt-b64"]
    ? Buffer.from(values["prompt-b64"] as string, "base64").toString("utf8")
    : (values["prompt"] as string);
  const prompts = values["prompts-b64"]
    ? JSON.parse(Buffer.from(values["prompts-b64"] as string, "base64").toString("utf8")) as string[]
    : undefined;
  const actionScript = values["action-script-b64"]
    ? JSON.parse(Buffer.from(values["action-script-b64"] as string, "base64").toString("utf8")) as ReplayAction[]
    : undefined;
  const submitCount =
    values["submit-count"] !== undefined
      ? Number.parseInt(values["submit-count"] as string, 10) || 1
      : prompt.startsWith("/") ? 2 : 1;

  return {
    prompt,
    prompts,
    actionScript,
    model: values["model"] as string,
    apiKey: values["api-key"] as string | undefined,
    baseURL: values["base-url"] as string | undefined,
    maxTurns: Number.parseInt(values["max-turns"] as string, 10) || 30,
    systemPrompt: values["system-prompt"] as string | undefined,
    waitMs: Number.parseInt(values["wait-ms"] as string, 10) || 12000,
    inputDelayMs: Number.parseInt(values["input-delay-ms"] as string, 10) || 300,
    submitCount,
    betweenPromptsMs: Number.parseInt(values["between-prompts-ms"] as string, 10) || 1200,
    interruptDelayMs: values["interrupt-delay-ms"] !== undefined
      ? Number.parseInt(values["interrupt-delay-ms"] as string, 10) || 0
      : undefined,
    interruptCount: Number.parseInt(values["interrupt-count"] as string, 10) || 0,
    expandDetailsDelayMs: values["expand-details-delay-ms"] !== undefined
      ? Number.parseInt(values["expand-details-delay-ms"] as string, 10) || 0
      : undefined,
    expandDetailsCount: Number.parseInt(values["expand-details-count"] as string, 10) || 0,
    searchQuery: values["search-query"] as string | undefined,
    searchDelayMs: values["search-delay-ms"] !== undefined
      ? Number.parseInt(values["search-delay-ms"] as string, 10) || 0
      : undefined,
    searchNextCount: Number.parseInt(values["search-next-count"] as string, 10) || 0,
    snapshotDir: resolve(snapshotDir),
    width: Number.parseInt(values["width"] as string, 10) || 120,
    height: Number.parseInt(values["height"] as string, 10) || 40,
  };
}

function ensureDir(dir: string): void {
  mkdirSync(dir, { recursive: true });
}

function writeSnapshot(baseDir: string, snapshot: FrameSnapshot): void {
  const frameName = String(snapshot.index).padStart(4, "0");
  writeFileSync(join(baseDir, `${frameName}.ansi`), snapshot.ansi, "utf8");
  writeFileSync(join(baseDir, `${frameName}.txt`), snapshot.text, "utf8");
}

function writeArtifacts(
  outputDir: string,
  stdout: RecordingOutput,
  stderr: RecordingOutput,
  snapshots: FrameSnapshot[],
  options: ReplayOptions,
  debugEvents: TUIDebugEvent[],
): void {
  writeFileSync(join(outputDir, "transcript.ansi"), stdout.getTranscript(), "utf8");
  writeFileSync(join(outputDir, "transcript.txt"), stripAnsi(stdout.getTranscript()), "utf8");
  writeFileSync(join(outputDir, "stderr.txt"), stripAnsi(stderr.getTranscript()), "utf8");
  writeFileSync(join(outputDir, "debug-events.json"), JSON.stringify(debugEvents, null, 2), "utf8");
  const completedRun = [...debugEvents].reverse().find((event) => event.type === "run_completed" || event.type === "run_failed");
  writeFileSync(
    join(outputDir, "meta.json"),
    JSON.stringify(
      {
        prompt: options.prompt,
        prompts: options.prompts,
        actionScript: options.actionScript,
        model: options.model,
        waitMs: options.waitMs,
        inputDelayMs: options.inputDelayMs,
        submitCount: options.submitCount,
        betweenPromptsMs: options.betweenPromptsMs,
        interruptDelayMs: options.interruptDelayMs,
        interruptCount: options.interruptCount,
        expandDetailsDelayMs: options.expandDetailsDelayMs,
        expandDetailsCount: options.expandDetailsCount,
        searchQuery: options.searchQuery,
        searchDelayMs: options.searchDelayMs,
        searchNextCount: options.searchNextCount,
        width: options.width,
        height: options.height,
        frameCount: snapshots.length,
        debugEventCount: debugEvents.length,
        completedRun,
        outputDir,
      },
      null,
      2,
    ),
    "utf8",
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

function mapReplayKey(key: ReplayKeyAction["key"]): string {
  switch (key) {
    case "enter":
      return "\r";
    case "escape":
      return "\u001b";
    case "backspace":
      return "\b";
    case "ctrl+o":
      return "\u000f";
    case "ctrl+f":
      return "\u0006";
    default:
      return "";
  }
}

async function waitForRunCompletion(
  debugEvents: TUIDebugEvent[],
  baselineCount: number,
  timeoutMs: number,
): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const next = debugEvents.slice(baselineCount).some(
      (event) => event.type === "run_completed" || event.type === "run_failed",
    );
    if (next) return;
    await sleep(100);
  }
}

async function sendSearchSequence(stdin: FakeTTYInput, options: ReplayOptions): Promise<number> {
  if (!options.searchQuery) return 0;
  const delay = options.searchDelayMs ?? options.waitMs;
  await sleep(delay);
  stdin.send("\u0006");
  await sleep(80);
  stdin.send(options.searchQuery);
  await sleep(80);
  for (let i = 0; i < options.searchNextCount; i += 1) {
    stdin.send("\r");
    await sleep(80);
  }
  return delay + 160 + options.searchNextCount * 80;
}

async function sendInterruptSequence(stdin: FakeTTYInput, options: ReplayOptions): Promise<number> {
  if (options.interruptCount <= 0) return 0;
  const delay = options.interruptDelayMs ?? options.waitMs;
  await sleep(delay);
  for (let i = 0; i < options.interruptCount; i += 1) {
    stdin.send("\u001b");
    await sleep(80);
  }
  return delay + options.interruptCount * 80;
}

async function sendExpandDetailsSequence(stdin: FakeTTYInput, options: ReplayOptions): Promise<number> {
  if (options.expandDetailsCount <= 0) return 0;
  const delay = options.expandDetailsDelayMs ?? options.waitMs;
  await sleep(delay);
  for (let i = 0; i < options.expandDetailsCount; i += 1) {
    stdin.send("\u000f");
    await sleep(80);
  }
  return delay + options.expandDetailsCount * 80;
}

async function runActionScript(
  stdin: FakeTTYInput,
  options: ReplayOptions,
  debugEvents: TUIDebugEvent[],
): Promise<void> {
  if (!options.actionScript || options.actionScript.length === 0) return;

  for (const action of options.actionScript) {
    if (action.type === "wait") {
      await sleep(action.ms);
      continue;
    }

    if (action.type === "text") {
      for (const char of action.value) {
        stdin.send(char);
        await sleep(action.delayMs ?? 40);
      }
      continue;
    }

    const key = mapReplayKey(action.key);
    const count = action.count ?? 1;
    for (let i = 0; i < count; i += 1) {
      const baselineEvents = debugEvents.length;
      stdin.send(key);
      if (action.key === "enter") {
        await waitForRunCompletion(debugEvents, baselineEvents, options.waitMs);
      }
      await sleep(action.delayMs ?? 80);
    }
  }
}

export async function runReplay(options: ReplayOptions): Promise<void> {
  const outputDir = options.snapshotDir;
  const framesDir = join(outputDir, "frames");
  ensureDir(framesDir);

  const stdin = new FakeTTYInput();
  const stdout = new RecordingOutput(options.width, options.height);
  const stderr = new RecordingOutput(options.width, options.height);
  const startedAt = Date.now();
  const snapshots: FrameSnapshot[] = [];
  const debugEvents: TUIDebugEvent[] = [];

  const renderOptions: RenderOptions = {
    stdin: stdin as unknown as NodeJS.ReadStream,
    stdout: stdout as unknown as NodeJS.WriteStream,
    stderr: stderr as unknown as NodeJS.WriteStream,
    exitOnCtrlC: false,
    patchConsole: false,
    onFrame: () => {
      const ansi = stdout.takeFrameChunk();
      const text = stripAnsi(ansi);
      const snapshot: FrameSnapshot = {
        index: snapshots.length,
        elapsedMs: Date.now() - startedAt,
        ansi,
        text,
      };
      snapshots.push(snapshot);
      writeSnapshot(framesDir, snapshot);
      writeArtifacts(outputDir, stdout, stderr, snapshots, options, debugEvents);
    },
  };

  const root = await createRoot(renderOptions);
  const replayAppOptions: TUIOptions = {
    ...options,
    debugHooks: {
      onEvent: (event) => {
        debugEvents.push(event);
        writeArtifacts(outputDir, stdout, stderr, snapshots, options, debugEvents);
      },
    },
  };
  root.render(React.createElement(App, { options: replayAppOptions }));

  await sleep(options.inputDelayMs);
  if (options.actionScript && options.actionScript.length > 0) {
    await runActionScript(stdin, options, debugEvents);
  } else {
    const prompts = options.prompts && options.prompts.length > 0 ? options.prompts : [options.prompt];
    for (let promptIndex = 0; promptIndex < prompts.length; promptIndex += 1) {
      const prompt = prompts[promptIndex]!;
      const baselineEvents = debugEvents.length;
      stdin.send(prompt);
      const submits =
        options.prompts && options.prompts.length > 0
          ? (prompt.startsWith("/") ? 2 : 1)
          : options.submitCount;
      for (let i = 0; i < submits; i += 1) {
        await sleep(60);
        stdin.send("\r");
      }
      if (promptIndex < prompts.length - 1) {
        if (prompt.startsWith("/")) {
          await sleep(options.betweenPromptsMs);
        } else {
          await waitForRunCompletion(debugEvents, baselineEvents, options.waitMs);
          await sleep(options.betweenPromptsMs);
        }
      }
    }
  }

  const interruptElapsed = await sendInterruptSequence(stdin, options);
  const detailsElapsed = await sendExpandDetailsSequence(stdin, options);
  const searchElapsed = await sendSearchSequence(stdin, options);
  const remainingWait = Math.max(0, options.waitMs - Math.max(interruptElapsed, detailsElapsed, searchElapsed));
  await sleep(remainingWait);
  writeArtifacts(outputDir, stdout, stderr, snapshots, options, debugEvents);
  root.unmount();
  stdin.end();
  stdin.destroy();
  stdout.end();
  stderr.end();
  writeArtifacts(outputDir, stdout, stderr, snapshots, options, debugEvents);

  process.stdout.write(`Saved replay to ${outputDir}\n`);
}

const isMain = process.argv[1] && (
  process.argv[1].endsWith("/replay.ts") ||
  process.argv[1].endsWith("/replay.js") ||
  process.argv[1].endsWith("\\replay.ts") ||
  process.argv[1].endsWith("\\replay.js")
);

if (isMain) {
  loadProjectEnv();
  runReplay(parseReplayArgs()).catch((error) => {
    const message = error instanceof Error ? error.stack ?? error.message : String(error);
    process.stderr.write(`${message}\n`);
    process.exit(1);
  });
  process.on("beforeExit", () => {
    process.exit(0);
  });
}
