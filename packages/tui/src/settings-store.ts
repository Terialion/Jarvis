// ============================================================================
// Settings store - compatibility wrapper over ~/.jarvis/config.json
// ============================================================================

import {
  getJarvisConfig,
  loadJarvisConfig,
  saveJarvisConfig,
  setJarvisConfig,
  type JarvisConfig,
} from '@jarvis/shared';

export interface UserSettings {
  model?: string;
  reasoning_effort?: JarvisConfig['reasoning_effort'];
  output_style?: 'default' | 'concise' | 'verbose';
  permission_mode?: 'workspace_write' | 'accept_edits' | 'bypass';
  max_turns?: number;
}

function toUserSettings(config: JarvisConfig): UserSettings {
  return {
    model: config.model,
    reasoning_effort: config.reasoning_effort,
    output_style: config.output_style,
    permission_mode: config.permission_mode,
    max_turns: config.max_turns,
  };
}

export function loadSettings(): UserSettings {
  return toUserSettings(loadJarvisConfig());
}

export function saveSettings(settings: UserSettings): void {
  saveJarvisConfig(settings);
}

export function getSetting<K extends keyof UserSettings>(key: K): UserSettings[K] | undefined {
  return getJarvisConfig(key as keyof JarvisConfig) as UserSettings[K] | undefined;
}

export function setSetting<K extends keyof UserSettings>(key: K, value: UserSettings[K]): void {
  setJarvisConfig(key as keyof JarvisConfig, value as JarvisConfig[keyof JarvisConfig]);
}
