// ============================================================================
// Plugin models — manifest and discovery types
// ============================================================================

export interface PluginManifest {
  name: string;
  version: string;
  enabled?: boolean;
  description?: string;
  author?: string;
  /** Relative paths from plugin root to component directories/files */
  commands?: string;
  agents?: string;
  skills?: string;
  hooks?: string;
  mcpServers?: string;
}

export type PluginIssue = {
  plugin: string;
  level: 'warning' | 'error';
  code: 'disabled' | 'duplicate' | 'invalid_manifest';
  message: string;
};

export interface PluginEntry {
  /** Plugin root directory on disk */
  rootDir: string;
  /** Parsed manifest */
  manifest: PluginManifest;
  /** Source scope: project, user, or system */
  source: 'project' | 'user' | 'system';
}

export interface PluginCommand {
  name: string;
  description: string;
  source: string;
  body: string;
}

export interface PluginHookConfig {
  hooks: Array<{
    name: string;
    stage: string;
    toolName?: string;
    handler: string;
  }>;
}
