// ============================================================================
// @jarvis/plugins — Plugin discovery, manifest parsing, and component loading
// ============================================================================

export { PluginRegistry } from './registry.js';
export { PluginDiscovery } from './discovery.js';
export { ComponentLoader } from './loader.js';
export type {
  PluginManifest,
  PluginEntry,
  PluginCommand,
  PluginHookConfig,
} from './models.js';
