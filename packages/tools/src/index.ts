// ============================================================================
// @jarvis/tools — barrel exports
// ============================================================================

// Registry
export {
  ToolRegistry,
  type ToolEntry,
  type ToolHandler,
  type ToolContext,
} from './registry.js';

// Runtime
export {
  ToolRuntime,
  ApprovalGate,
  type ToolRuntimeOptions,
  type ApprovalResult,
} from './runtime.js';

// Builtin tools (individual entries + schemas)
export { bashTool, bashSchema } from './builtin/bash.js';
export { readFileTool, readFileSchema } from './builtin/file-read.js';
export { writeFileTool, writeFileSchema } from './builtin/file-write.js';
export { editFileTool, editFileSchema } from './builtin/file-edit.js';
export { globTool, globSchema } from './builtin/glob.js';
export { grepTool, grepSchema } from './builtin/grep.js';
export { webSearchTool, webSearchSchema } from './builtin/web-search.js';
export { webFetchTool, webFetchSchema } from './builtin/web-fetch.js';

import type { ToolEntry } from './registry.js';
import { bashTool } from './builtin/bash.js';
import { readFileTool } from './builtin/file-read.js';
import { writeFileTool } from './builtin/file-write.js';
import { editFileTool } from './builtin/file-edit.js';
import { globTool } from './builtin/glob.js';
import { grepTool } from './builtin/grep.js';
import { webSearchTool } from './builtin/web-search.js';
import { webFetchTool } from './builtin/web-fetch.js';

/** All builtin tool entries in one array. */
export const allBuiltinTools: ToolEntry[] = [
  bashTool,
  readFileTool,
  writeFileTool,
  editFileTool,
  globTool,
  grepTool,
  webSearchTool,
  webFetchTool,
];
