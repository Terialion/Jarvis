// ============================================================================
// Settings store — persistent settings.json at ~/.jarvis/settings.json
// ============================================================================

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';

export interface UserSettings {
  model?: string;
  output_style?: 'default' | 'concise' | 'verbose';
  permission_mode?: 'workspace_write' | 'accept_edits' | 'bypass';
  max_turns?: number;
}

const JARVIS_DIR = join(homedir(), '.jarvis');
const SETTINGS_PATH = join(JARVIS_DIR, 'settings.json');

function ensureDir(): void {
  if (!existsSync(JARVIS_DIR)) {
    mkdirSync(JARVIS_DIR, { recursive: true });
  }
}

export function loadSettings(): UserSettings {
  try {
    if (!existsSync(SETTINGS_PATH)) return {};
    const raw = readFileSync(SETTINGS_PATH, 'utf-8');
    return JSON.parse(raw) as UserSettings;
  } catch {
    return {};
  }
}

export function saveSettings(settings: UserSettings): void {
  ensureDir();
  const current = loadSettings();
  const merged = { ...current, ...settings };
  writeFileSync(SETTINGS_PATH, JSON.stringify(merged, null, 2) + '\n', 'utf-8');
}

export function getSetting<K extends keyof UserSettings>(key: K): UserSettings[K] | undefined {
  return loadSettings()[key];
}

export function setSetting<K extends keyof UserSettings>(key: K, value: UserSettings[K]): void {
  saveSettings({ [key]: value });
}
