import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface ProviderConfig {
  base_url?: string;
  api_key?: string;
}

export interface SandboxSettings {
  /** Enable restricted local sandbox. Default: true */
  enabled?: boolean;
  /** Allow network commands (curl, wget, git push). Default: true */
  allowNetwork?: boolean;
  /** Allow file operations outside project root. Default: false */
  allowOutsideProject?: boolean;
  /** Extra blocked command patterns (regex strings) */
  extraBlockedPatterns?: string[];
  /** Extra allowed command patterns that bypass caution checks */
  extraAllowedPatterns?: string[];
}

export interface JarvisConfig {
  /** @deprecated Use active_model */
  model?: string;
  /** Active model name. Takes precedence over `model`. */
  active_model?: string;
  api_key?: string;
  base_url?: string;
  /** Per-provider credentials. Keyed by provider name (e.g. "deepseek", "xiaomi"). */
  providers?: Record<string, ProviderConfig>;
  /** Sandbox settings for restricted local mode */
  sandbox?: SandboxSettings;
  reasoning_effort?: JarvisReasoningEffort;
  output_style?: "default" | "concise" | "verbose";
  permission_mode?: "workspace_write" | "accept_edits" | "bypass";
  max_turns?: number;
  system_prompt?: string;
}

export const JARVIS_REASONING_EFFORTS = [
  "auto",
  "minimal",
  "low",
  "medium",
  "high",
  "xhigh",
  "max",
] as const;

export type JarvisReasoningEffort = (typeof JARVIS_REASONING_EFFORTS)[number];

const JARVIS_DIR = join(homedir(), ".jarvis");
const CONFIG_PATH = join(JARVIS_DIR, "config.json");
const LEGACY_SETTINGS_PATH = join(JARVIS_DIR, "settings.json");
const DEFAULT_MODEL = "deepseek-chat";
const DEFAULT_BASE_URL = "https://api.deepseek.com/v1";
const DEFAULT_MAX_TURNS = 30;
const DEFAULT_PERMISSION_MODE: NonNullable<JarvisConfig["permission_mode"]> = "workspace_write";
const DEFAULT_OUTPUT_STYLE: NonNullable<JarvisConfig["output_style"]> = "default";
const DEFAULT_REASONING_EFFORT: NonNullable<JarvisConfig["reasoning_effort"]> = "high";

function ensureDir(): void {
  if (!existsSync(JARVIS_DIR)) {
    mkdirSync(JARVIS_DIR, { recursive: true });
  }
}

function readJsonFile<T>(filePath: string): T | null {
  try {
    if (!existsSync(filePath)) return null;
    return JSON.parse(readFileSync(filePath, "utf-8")) as T;
  } catch {
    return null;
  }
}

export function getJarvisConfigPath(): string {
  return CONFIG_PATH;
}

export function loadJarvisConfig(): JarvisConfig {
  const config = readJsonFile<JarvisConfig>(CONFIG_PATH) ?? {};
  const legacy = readJsonFile<JarvisConfig>(LEGACY_SETTINGS_PATH) ?? {};
  return { ...legacy, ...config };
}

export function resolveJarvisConfigDefaults(config: JarvisConfig = loadJarvisConfig()): Required<Pick<
  JarvisConfig,
  "base_url" | "reasoning_effort" | "max_turns" | "permission_mode" | "output_style"
>> &
  Pick<JarvisConfig, "model" | "active_model" | "api_key" | "system_prompt"> {
  const activeModel = config.active_model ?? config.model;
  return {
    model: config.model,
    active_model: activeModel ?? process.env["JARVIS_LLM_MODEL"] ?? process.env["JARVIS_MODEL"] ?? DEFAULT_MODEL,
    api_key: config.api_key ?? process.env["JARVIS_LLM_API_KEY"] ?? process.env["OPENAI_API_KEY"],
    base_url: config.base_url ?? process.env["JARVIS_LLM_BASE_URL"] ?? process.env["JARVIS_BASE_URL"] ?? DEFAULT_BASE_URL,
    reasoning_effort:
      normalizeJarvisReasoningEffort(
        config.reasoning_effort
          ?? process.env["JARVIS_LLM_REASONING_EFFORT"]
          ?? process.env["JARVIS_REASONING_EFFORT"],
      ) ?? DEFAULT_REASONING_EFFORT,
    max_turns: config.max_turns ?? DEFAULT_MAX_TURNS,
    permission_mode: config.permission_mode ?? DEFAULT_PERMISSION_MODE,
    output_style: config.output_style ?? DEFAULT_OUTPUT_STYLE,
    system_prompt: config.system_prompt,
  };
}

export function needsJarvisOnboarding(config: JarvisConfig = loadJarvisConfig()): boolean {
  if (!existsSync(CONFIG_PATH)) return true;

  const resolved = resolveJarvisConfigDefaults(config);
  return !Boolean(config.model?.trim())
    || !Boolean(resolved.api_key?.trim())
    || !Boolean(config.base_url?.trim())
    || !(typeof config.max_turns === "number" && Number.isFinite(config.max_turns));
}

export function saveJarvisConfig(config: JarvisConfig): void {
  ensureDir();
  const current = loadJarvisConfig();
  const merged = { ...current, ...config };
  writeFileSync(CONFIG_PATH, JSON.stringify(merged, null, 2) + "\n", "utf-8");
}

export function getJarvisConfig<K extends keyof JarvisConfig>(key: K): JarvisConfig[K] | undefined {
  return loadJarvisConfig()[key];
}

export function setJarvisConfig<K extends keyof JarvisConfig>(key: K, value: JarvisConfig[K]): void {
  saveJarvisConfig({ [key]: value });
}

export function normalizeJarvisReasoningEffort(
  value: string | null | undefined,
): JarvisReasoningEffort | undefined {
  if (!value) return undefined;
  const normalized = value.trim().toLowerCase();
  return JARVIS_REASONING_EFFORTS.includes(normalized as JarvisReasoningEffort)
    ? (normalized as JarvisReasoningEffort)
    : undefined;
}
