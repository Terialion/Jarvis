// ============================================================================
// Builtin tool tests — all builtin tools
// ============================================================================

import { describe, it, expect, afterAll, beforeAll } from 'vitest';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import type { ToolHandler, ToolContext } from '../registry.js';
import { bashTool } from '../builtin/bash.js';
import { readFileTool } from '../builtin/file-read.js';
import { writeFileTool } from '../builtin/file-write.js';
import { editFileTool } from '../builtin/file-edit.js';
import { globTool } from '../builtin/glob.js';
import { grepTool } from '../builtin/grep.js';
import { webSearchTool } from '../builtin/web-search.js';
import { webFetchTool } from '../builtin/web-fetch.js';
import {
  askUserQuestionTool,
  setAskUserQuestionBridge,
  type AskQuestionDef,
} from '../builtin/ask-user-question.js';
import { taskCreateTool, taskUpdateTool, taskListTool, taskGetTool } from '../builtin/task.js';
import { enterPlanModeTool, exitPlanModeTool } from '../builtin/plan-mode.js';
import { notebookEditTool } from '../builtin/notebook-edit.js';
import { cronCreateTool, cronDeleteTool, cronListTool, scheduleWakeupTool } from '../builtin/cron.js';
import { getCronScheduler } from '../builtin/cron-scheduler.js';
import { enterWorktreeTool, exitWorktreeTool } from '../builtin/worktree.js';
import { createAgentTool, type AgentPool } from '../builtin/agent.js';
import { createListMcpResourcesTool, createReadMcpResourceTool, type McpResourceClient } from '../builtin/mcp-resource.js';

const ctx: ToolContext = {};

// ============================================================================
// Bash tool
// ============================================================================

describe('bash tool', () => {
  it('schema has correct format', () => {
    expect(bashTool.name).toBe('bash');
    expect(bashTool.schema.type).toBe('function');
    const fn = bashTool.schema.function as Record<string, unknown>;
    expect(fn.name).toBe('bash');
    expect(fn.parameters).toBeDefined();
  });

  it('executes a simple echo command', async () => {
    const result = await bashTool.handler({ command: 'echo hello' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.exitCode).toBe(0);
    expect(parsed.stdout).toContain('hello');
  });

  it('captures stderr', async () => {
    // Command that outputs to stderr
    const result = await bashTool.handler(
      { command: 'echo error >&2' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.stderr).toContain('error');
  });

  it('handles command not found', async () => {
    const result = await bashTool.handler(
      { command: 'nonexistent_command_xyz_123' },
      ctx,
    );
    const parsed = JSON.parse(result);
    // Non-zero exit on command-not-found
    expect(parsed.exitCode).not.toBe(0);
  });

  it('handles empty command', async () => {
    const result = await bashTool.handler({ command: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No command provided');
  });
});

// ============================================================================
// Read file tool
// ============================================================================

describe('read_file tool', () => {
  it('schema has correct format', () => {
    expect(readFileTool.name).toBe('read_file');
    expect(readFileTool.schema.type).toBe('function');
  });

  it('reads a known file with line numbers', async () => {
    // Read the package.json of the tools package itself
    const result = await readFileTool.handler(
      { path: 'D:/agent/Jarvis/packages/tools/package.json' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.content).toBeDefined();
    expect(parsed.content).toContain('@jarvis/tools');
    expect(parsed.totalLines).toBeGreaterThan(0);
  });

  it('applies offset correctly', async () => {
    const result = await readFileTool.handler(
      {
        path: 'D:/agent/Jarvis/packages/tools/package.json',
        offset: 3,
        limit: 1,
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.content).toBeDefined();
    // Line 3 should be the version line
    expect(parsed.content).toContain('"version"');
    expect(parsed.linesRead).toBe(1);
  });

  it('returns error for missing file', async () => {
    const result = await readFileTool.handler(
      { path: 'D:/agent/Jarvis/packages/tools/nonexistent_file.txt' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('File not found');
  });

  it('handles empty path', async () => {
    const result = await readFileTool.handler({ path: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No path provided');
  });

  it('handles offset beyond file length', async () => {
    const result = await readFileTool.handler(
      {
        path: 'D:/agent/Jarvis/packages/tools/package.json',
        offset: 99999,
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.message).toContain('Offset');
  });

  it('has cat -n format (tab-separated line numbers)', async () => {
    const result = await readFileTool.handler(
      { path: 'D:/agent/Jarvis/packages/tools/package.json', limit: 2 },
      ctx,
    );
    const parsed = JSON.parse(result);
    const lines = parsed.content.split('\n');
    for (const line of lines.slice(0, 1)) {
      // Should have a tab character separating line number from content
      expect(line).toMatch(/^\s+\d+\t/);
    }
  });
});

// ============================================================================
// Write file tool (smoke tests)
// ============================================================================

describe('write_file tool', () => {
  it('schema has correct format', () => {
    expect(writeFileTool.name).toBe('write_file');
    expect(writeFileTool.schema.type).toBe('function');
  });

  it('rejects empty path', async () => {
    const result = await writeFileTool.handler({ path: '', content: 'test' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No path provided');
  });
});

// ============================================================================
// Edit file tool (smoke tests)
// ============================================================================

describe('edit_file tool', () => {
  it('schema has correct format', () => {
    expect(editFileTool.name).toBe('edit_file');
    expect(editFileTool.schema.type).toBe('function');
  });

  it('rejects missing file', async () => {
    const result = await editFileTool.handler(
      { path: '/nonexistent/file.txt', old_string: 'a', new_string: 'b' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('File not found');
  });
});

// ============================================================================
// Glob tool
// ============================================================================

describe('glob tool', () => {
  it('schema has correct format', () => {
    expect(globTool.name).toBe('glob');
    expect(globTool.schema.type).toBe('function');
  });

  it('finds files with *.json pattern', async () => {
    const result = await globTool.handler(
      { pattern: '*.json', path: 'D:/agent/Jarvis/packages/tools' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    expect(Array.isArray(parsed.matches)).toBe(true);
    // Should find package.json at minimum
    expect(parsed.matches).toContain('package.json');
  });

  it('finds files with ** pattern', async () => {
    const result = await globTool.handler(
      { pattern: '**/*.ts', path: 'D:/agent/Jarvis/packages/tools/src' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    // Should find at least index.ts and registry.ts
    expect(parsed.matches.some((m: string) => m.endsWith('index.ts'))).toBe(true);
    expect(parsed.matches.some((m: string) => m.endsWith('registry.ts'))).toBe(true);
  });

  it('rejects empty pattern', async () => {
    const result = await globTool.handler({ pattern: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No pattern provided');
  });
});

// ============================================================================
// Grep tool
// ============================================================================

describe('grep tool', () => {
  it('schema has correct format', () => {
    expect(grepTool.name).toBe('grep');
    expect(grepTool.schema.type).toBe('function');
  });

  it('finds text matching a pattern', async () => {
    const result = await grepTool.handler(
      { pattern: 'ToolRegistry', path: 'D:/agent/Jarvis/packages/tools/src' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.matches).toBeDefined();
    expect(Array.isArray(parsed.matches)).toBe(true);
    expect(parsed.matches.length).toBeGreaterThan(0);
    for (const match of parsed.matches) {
      expect(match).toContain('ToolRegistry');
    }
  });

  it('supports files_with_matches mode', async () => {
    const result = await grepTool.handler(
      {
        pattern: 'export.*ToolRegistry',
        path: 'D:/agent/Jarvis/packages/tools/src',
        output_mode: 'files_with_matches',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.files).toBeDefined();
    expect(Array.isArray(parsed.files)).toBe(true);
    expect(parsed.files.length).toBeGreaterThan(0);
  });

  it('rejects empty pattern', async () => {
    const result = await grepTool.handler({ pattern: '' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No pattern provided');
  });

  it('rejects invalid regex', async () => {
    const result = await grepTool.handler({ pattern: '[invalid[', path: '/tmp' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Invalid regex');
  });
});

// ============================================================================
// AskUserQuestion tool
// ============================================================================

describe('ask_user_question tool', () => {
  it('schema has correct format', () => {
    expect(askUserQuestionTool.name).toBe('ask_user_question');
    expect(askUserQuestionTool.schema.type).toBe('function');
    expect(askUserQuestionTool.isAsync).toBe(true);
  });

  it('returns error when no bridge is set', async () => {
    setAskUserQuestionBridge(null);
    const result = await askUserQuestionTool.handler(
      { questions: [{ question: 'Test?', header: 'Test', options: [{ label: 'A', description: 'Option A' }] }] },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('no TUI bridge');
  });

  it('returns error when questions array is empty', async () => {
    const result = await askUserQuestionTool.handler({ questions: [] }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No questions provided');
  });

  it('calls bridge and returns answers when bridge is set', async () => {
    const mockBridge = async (_questions: AskQuestionDef[]) => {
      return { 'Test?': 'A' };
    };
    setAskUserQuestionBridge(mockBridge);

    const result = await askUserQuestionTool.handler(
      { questions: [{ question: 'Test?', header: 'Test', options: [{ label: 'A', description: 'Option A' }] }] },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.answers).toEqual({ 'Test?': 'A' });
  });

  it('handles bridge rejection (user cancelled)', async () => {
    const mockBridge = async () => {
      throw new Error('User cancelled');
    };
    setAskUserQuestionBridge(mockBridge);

    const result = await askUserQuestionTool.handler(
      { questions: [{ question: 'Test?', header: 'Test', options: [{ label: 'A', description: 'Option A' }] }] },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('cancelled');
    expect(parsed.error).toContain('User cancelled');
  });
});

// ============================================================================
// Task tools — task_create / task_update / task_list
// ============================================================================

describe('task tools', () => {
  it('task_create schema has correct format', () => {
    expect(taskCreateTool.name).toBe('task_create');
    expect(taskCreateTool.schema.type).toBe('function');
  });

  it('task_create creates tasks and returns them', async () => {
    const result = await taskCreateTool.handler(
      {
        tasks: [
          { subject: 'Fix login bug', description: 'Fix the login form validation' },
          { subject: 'Add tests', description: 'Add unit tests for auth', status: 'pending' },
        ],
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.message).toContain('Created 2 task(s)');
    expect(parsed.tasks).toHaveLength(2);
    expect(parsed.tasks[0].id).toMatch(/^task_\d+$/);
    expect(parsed.tasks[0].subject).toBe('Fix login bug');
    expect(parsed.tasks[0].status).toBe('pending');
  });

  it('task_create defaults status to pending', async () => {
    const result = await taskCreateTool.handler(
      { tasks: [{ subject: 'Test', description: 'Test desc' }] },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.tasks[0].status).toBe('pending');
  });

  it('task_create rejects empty tasks array', async () => {
    const result = await taskCreateTool.handler({ tasks: [] }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('No tasks provided');
  });

  it('task_update updates task status', async () => {
    // Create a task first
    const createResult = await taskCreateTool.handler(
      { tasks: [{ subject: 'Test task', description: 'Testing' }] },
      ctx,
    );
    const { tasks } = JSON.parse(createResult) as { tasks: Array<{ id: string }> };
    const taskId = tasks[0]!.id;

    // Mark it in_progress
    const updateResult = await taskUpdateTool.handler({ taskId, status: 'in_progress' }, ctx);
    const parsed = JSON.parse(updateResult);
    expect(parsed.task.status).toBe('in_progress');

    // Mark it completed
    const completeResult = await taskUpdateTool.handler({ taskId, status: 'completed' }, ctx);
    const completeParsed = JSON.parse(completeResult);
    expect(completeParsed.task.status).toBe('completed');
  });

  it('task_update rejects second in_progress', async () => {
    const r1 = await taskCreateTool.handler(
      { tasks: [{ subject: 'Task 1', description: 'First' }] },
      ctx,
    );
    const r2 = await taskCreateTool.handler(
      { tasks: [{ subject: 'Task 2', description: 'Second' }] },
      ctx,
    );
    const id1 = (JSON.parse(r1) as { tasks: Array<{ id: string }> }).tasks[0]!.id;
    const id2 = (JSON.parse(r2) as { tasks: Array<{ id: string }> }).tasks[0]!.id;

    // First in_progress succeeds
    await taskUpdateTool.handler({ taskId: id1, status: 'in_progress' }, ctx);

    // Second in_progress should fail
    const result = await taskUpdateTool.handler({ taskId: id2, status: 'in_progress' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('already in_progress');
  });

  it('task_update deletes tasks', async () => {
    const createResult = await taskCreateTool.handler(
      { tasks: [{ subject: 'Temp task', description: 'Will be deleted' }] },
      ctx,
    );
    const taskId = (JSON.parse(createResult) as { tasks: Array<{ id: string }> }).tasks[0]!.id;

    const result = await taskUpdateTool.handler({ taskId, status: 'deleted' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.message).toContain('Deleted task');
  });

  it('task_update returns error for unknown task', async () => {
    const result = await taskUpdateTool.handler({ taskId: 'nonexistent', status: 'completed' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Task not found');
  });

  it('task_list lists tasks with counts', async () => {
    const listResult = await taskListTool.handler({}, ctx);
    const parsed = JSON.parse(listResult);
    expect(Array.isArray(parsed.tasks)).toBe(true);
    expect(parsed.counts).toBeDefined();
    expect(typeof parsed.counts.pending).toBe('number');
    expect(typeof parsed.counts.in_progress).toBe('number');
    expect(typeof parsed.counts.completed).toBe('number');
  });

  it('task_list supports status filter', async () => {
    const result = await taskListTool.handler({ status: 'completed' }, ctx);
    const parsed = JSON.parse(result);
    for (const t of parsed.tasks) {
      expect(t.status).toBe('completed');
    }
  });
});

// ============================================================================
// Plan mode tools — enter_plan_mode / exit_plan_mode
// ============================================================================

describe('plan mode tools', () => {
  it('enter_plan_mode schema has correct format', () => {
    expect(enterPlanModeTool.name).toBe('enter_plan_mode');
    expect(enterPlanModeTool.schema.type).toBe('function');
  });

  it('exit_plan_mode schema has correct format', () => {
    expect(exitPlanModeTool.name).toBe('exit_plan_mode');
    expect(exitPlanModeTool.schema.type).toBe('function');
  });

  it('enter_plan_mode returns plan_mode flag and message', async () => {
    const result = await enterPlanModeTool.handler(
      { task: 'Add dark mode support' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.plan_mode).toBe(true);
    expect(parsed.message).toContain('Add dark mode support');
    expect(parsed.message).toContain('Entering plan mode');
  });

  it('exit_plan_mode returns formatted plan with steps', async () => {
    const result = await exitPlanModeTool.handler(
      {
        summary: 'Add dark mode to settings',
        steps: [
          { step: 'Add theme context', files: ['theme.tsx'], verification: 'Context provides dark/light value' },
          { step: 'Create toggle component', files: ['Toggle.tsx'] },
          { step: 'Apply styles to all components' },
        ],
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.plan_mode).toBe(false);
    expect(parsed.message).toContain('## Plan: Add dark mode to settings');
    expect(parsed.message).toContain('1. Add theme context');
    expect(parsed.message).toContain('[theme.tsx]');
    expect(parsed.message).toContain('verify: Context provides dark/light value');
    expect(parsed.message).toContain('2. Create toggle component');
    expect(parsed.message).toContain('3. Apply styles to all components');
  });

  it('exit_plan_mode works without optional steps', async () => {
    const result = await exitPlanModeTool.handler(
      { summary: 'Simple plan' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.plan_mode).toBe(false);
    expect(parsed.message).toContain('## Plan: Simple plan');
  });
});

// ============================================================================
// Notebook edit tool — notebook_edit
// ============================================================================

describe('notebook_edit tool', () => {
  const testNotebookPath = 'D:/agent/Jarvis/packages/tools/src/__tests__/test_notebook.ipynb';

  afterAll(() => {
    try {
      const fs = require('node:fs');
      if (fs.existsSync(testNotebookPath)) {
        fs.unlinkSync(testNotebookPath);
      }
    } catch {
      // ignore cleanup errors
    }
  });

  it('schema has correct format', () => {
    expect(notebookEditTool.name).toBe('notebook_edit');
    expect(notebookEditTool.schema.type).toBe('function');
  });

  it('inserts a new cell into a new notebook', async () => {
    const fs = require('node:fs');
    const nb = {
      cells: [],
      metadata: {},
      nbformat: 4,
      nbformat_minor: 5,
    };
    fs.writeFileSync(testNotebookPath, JSON.stringify(nb, null, 1) + '\n');

    const result = await notebookEditTool.handler(
      {
        notebook_path: testNotebookPath,
        new_source: 'print("hello")',
        cell_type: 'code',
        edit_mode: 'insert',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.ok).toBe(true);

    const content = JSON.parse(fs.readFileSync(testNotebookPath, 'utf-8'));
    expect(content.cells).toHaveLength(1);
    expect(content.cells[0].cell_type).toBe('code');
    expect(content.cells[0].source[0]).toBe('print("hello")');
  });

  it('inserts a cell after a specific index', async () => {
    const fs = require('node:fs');
    const nb = {
      cells: [
        { cell_type: 'code', source: ['# first cell\n'], metadata: {}, outputs: [], execution_count: null, id: 'c1' },
        { cell_type: 'code', source: ['# second cell\n'], metadata: {}, outputs: [], execution_count: null, id: 'c2' },
      ],
      metadata: {},
      nbformat: 4,
      nbformat_minor: 5,
    };
    fs.writeFileSync(testNotebookPath, JSON.stringify(nb, null, 1) + '\n');

    const result = await notebookEditTool.handler(
      {
        notebook_path: testNotebookPath,
        new_source: '# middle',
        cell_type: 'markdown',
        cell_number: 0,
        edit_mode: 'insert',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.ok).toBe(true);
    expect(parsed.cell_number).toBe(1);

    const content = JSON.parse(fs.readFileSync(testNotebookPath, 'utf-8'));
    expect(content.cells).toHaveLength(3);
    expect(content.cells[0].source[0]).toBe('# first cell\n');
    expect(content.cells[1].cell_type).toBe('markdown');
    expect(content.cells[1].source[0]).toBe('# middle');
    expect(content.cells[2].source[0]).toBe('# second cell\n');
  });

  it('replaces an existing cell', async () => {
    const fs = require('node:fs');
    const nb = {
      cells: [
        { cell_type: 'code', source: ['old_code\n'], metadata: {}, outputs: [], execution_count: null, id: 'c1' },
      ],
      metadata: {},
      nbformat: 4,
      nbformat_minor: 5,
    };
    fs.writeFileSync(testNotebookPath, JSON.stringify(nb, null, 1) + '\n');

    const result = await notebookEditTool.handler(
      {
        notebook_path: testNotebookPath,
        new_source: 'new_code',
        cell_type: 'code',
        cell_number: 0,
        edit_mode: 'replace',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.ok).toBe(true);

    const content = JSON.parse(fs.readFileSync(testNotebookPath, 'utf-8'));
    expect(content.cells[0].source[0]).toBe('new_code');
  });

  it('deletes a cell', async () => {
    const fs = require('node:fs');
    const nb = {
      cells: [
        { cell_type: 'code', source: ['# keep\n'], metadata: {}, outputs: [], execution_count: null, id: 'c1' },
        { cell_type: 'code', source: ['# delete\n'], metadata: {}, outputs: [], execution_count: null, id: 'c2' },
      ],
      metadata: {},
      nbformat: 4,
      nbformat_minor: 5,
    };
    fs.writeFileSync(testNotebookPath, JSON.stringify(nb, null, 1) + '\n');

    const result = await notebookEditTool.handler(
      {
        notebook_path: testNotebookPath,
        new_source: '',
        cell_number: 1,
        edit_mode: 'delete',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.ok).toBe(true);

    const content = JSON.parse(fs.readFileSync(testNotebookPath, 'utf-8'));
    expect(content.cells).toHaveLength(1);
    expect(content.cells[0].source[0]).toBe('# keep\n');
  });

  it('rejects non-.ipynb files', async () => {
    const result = await notebookEditTool.handler(
      {
        notebook_path: 'D:/agent/Jarvis/packages/tools/package.json',
        new_source: 'test',
        edit_mode: 'insert',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Jupyter notebook');
  });

  it('rejects out-of-range cell_number in replace mode', async () => {
    const fs = require('node:fs');
    const nb = { cells: [], metadata: {}, nbformat: 4, nbformat_minor: 5 };
    fs.writeFileSync(testNotebookPath, JSON.stringify(nb, null, 1) + '\n');

    const result = await notebookEditTool.handler(
      {
        notebook_path: testNotebookPath,
        new_source: 'test',
        cell_number: 0,
        edit_mode: 'replace',
      },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('out of range');
  });
});

// ============================================================================
// read_file — image support
// ============================================================================

describe('read_file image support', () => {
  let tmpDir: string;

  beforeAll(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'jarvis-test-'));
  });

  afterAll(() => {
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
  });

  it('detects PNG and returns base64 + content placeholder', async () => {
    // Minimal valid 1x1 red PNG (67 bytes)
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==',
      'base64',
    );
    const pngPath = join(tmpDir, 'test.png');
    writeFileSync(pngPath, png);

    const result = await readFileTool.handler({ path: pngPath }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.type).toBe('image');
    expect(parsed.mimeType).toBe('image/png');
    expect(parsed.base64).toBeDefined();
    expect(parsed.content).toContain('[Image:');
    expect(parsed.content).toContain('.png');
    expect(parsed.size).toBe(png.length);
  });

  it('detects JPEG and sets correct MIME type', async () => {
    // Minimal JPEG (rough, but valid enough for extension detection)
    const jpgPath = join(tmpDir, 'photo.jpg');
    writeFileSync(jpgPath, Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0, 0, 0, 0]));

    const result = await readFileTool.handler({ path: jpgPath }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.type).toBe('image');
    expect(parsed.mimeType).toBe('image/jpeg');
    expect(parsed.base64).toBeDefined();
  });

  it('detects GIF, WebP, BMP, SVG extensions', async () => {
    for (const ext of ['.gif', '.webp', '.bmp', '.svg']) {
      const imgPath = join(tmpDir, `test${ext}`);
      writeFileSync(imgPath, Buffer.from([0x00])); // dummy content

      const result = await readFileTool.handler({ path: imgPath }, ctx);
      const parsed = JSON.parse(result);
      expect(parsed.type).toBe('image');
      expect(parsed.base64).toBeDefined();
    }
  });

  it('returns text content for non-image files unchanged', async () => {
    const txtPath = join(tmpDir, 'notes.txt');
    writeFileSync(txtPath, 'hello world\nline two');

    const result = await readFileTool.handler({ path: txtPath }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.type).toBeUndefined();
    expect(parsed.content).toContain('hello world');
    expect(parsed.content).toContain('line two');
    expect(parsed.totalLines).toBe(2);
  });
});

// ============================================================================
// read_file — PDF support
// ============================================================================

describe('read_file PDF support', () => {
  it('detects PDF by extension', async () => {
    // Create a minimal valid PDF
    const pdfContent = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n194\n%%EOF`;
    const tmpDir = mkdtempSync(join(tmpdir(), 'jarvis-pdf-'));
    const pdfPath = join(tmpDir, 'test.pdf');
    writeFileSync(pdfPath, pdfContent);

    try {
      const result = await readFileTool.handler({ path: pdfPath }, ctx);
      const parsed = JSON.parse(result);
      // Either extracts text successfully or fails with an error
      // (pdf-parse may or may not work depending on environment)
      if (parsed.error) {
        // If pdf-parse can't parse it, error should not be "File not found"
        expect(parsed.error).not.toContain('File not found');
      } else {
        expect(parsed.content).toBeDefined();
        expect(typeof parsed.totalLines).toBe('number');
        expect(typeof parsed.totalPages).toBe('number');
      }
    } finally {
      try { rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
    }
  });

  it('supports pages parameter', async () => {
    const tmpDir = mkdtempSync(join(tmpdir(), 'jarvis-pdf2-'));
    const pdfPath = join(tmpDir, 'test.pdf');
    const pdfContent = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n194\n%%EOF`;
    writeFileSync(pdfPath, pdfContent);

    try {
      const result = await readFileTool.handler({ path: pdfPath, pages: '1' }, ctx);
      const parsed = JSON.parse(result);
      if (!parsed.error) {
        expect(parsed.pagesRequested).toEqual([1]);
      }
    } finally {
      try { rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
    }
  });
});

// ============================================================================
// task_get tool
// ============================================================================

describe('task_get tool', () => {
  it('schema has correct format', () => {
    expect(taskGetTool.name).toBe('task_get');
    expect(taskGetTool.schema.type).toBe('function');
  });

  it('returns full task details for a known task', async () => {
    const createResult = await taskCreateTool.handler(
      { tasks: [{ subject: 'Get test', description: 'Testing task_get' }] },
      ctx,
    );
    const taskId = (JSON.parse(createResult) as { tasks: Array<{ id: string }> }).tasks[0]!.id;

    const result = await taskGetTool.handler({ taskId }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.id).toBe(taskId);
    expect(parsed.subject).toBe('Get test');
    expect(parsed.description).toBe('Testing task_get');
    expect(parsed.status).toBe('pending');
    expect(typeof parsed.createdAt).toBe('number');
  });

  it('returns error for unknown task', async () => {
    const result = await taskGetTool.handler({ taskId: 'nonexistent_999' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Task not found');
  });

  it('returns error when taskId is missing', async () => {
    const result = await taskGetTool.handler({}, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Task not found');
  });
});

// ============================================================================
// Cron tools — cron_create, cron_delete, cron_list, schedule_wakeup
// ============================================================================

describe('cron tools', () => {
  afterAll(() => {
    getCronScheduler().destroy();
  });

  it('cron_create schema has correct format', () => {
    expect(cronCreateTool.name).toBe('cron_create');
    expect(cronCreateTool.schema.type).toBe('function');
  });

  it('cron_create schedules a job and returns jobId', async () => {
    const result = await cronCreateTool.handler(
      { cron: '0 9 * * 1-5', prompt: 'Morning standup reminder', recurring: true },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.jobId).toMatch(/^cron_\d+$/);
    expect(parsed.cron).toBe('0 9 * * 1-5');
    expect(parsed.nextFireAt).toBeDefined();
    expect(parsed.recurring).toBe(true);
  });

  it('cron_create supports one-shot (recurring=false)', async () => {
    const result = await cronCreateTool.handler(
      { cron: '30 14 28 2 *', prompt: 'One-time check', recurring: false },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.jobId).toBeDefined();
    expect(parsed.recurring).toBe(false);
  });

  it('cron_create rejects invalid cron expressions', async () => {
    const result = await cronCreateTool.handler(
      { cron: 'invalid', prompt: 'test' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('exactly 5 fields');
  });

  it('cron_create rejects missing parameters', async () => {
    const result = await cronCreateTool.handler({}, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Missing');
  });

  it('cron_list lists scheduled jobs', async () => {
    const result = await cronListTool.handler({}, ctx);
    const parsed = JSON.parse(result);
    expect(Array.isArray(parsed.jobs)).toBe(true);
    // Should have at least the jobs we created above
    expect(parsed.jobs.length).toBeGreaterThanOrEqual(2);
    for (const j of parsed.jobs) {
      expect(j.id).toMatch(/^cron_\d+$/);
      expect(j.cron).toBeDefined();
      expect(j.nextFireAt).toBeDefined();
    }
  });

  it('cron_delete cancels a job', async () => {
    // Create a job
    const createResult = await cronCreateTool.handler(
      { cron: '*/15 * * * *', prompt: 'Check status', recurring: false },
      ctx,
    );
    const { jobId } = JSON.parse(createResult) as { jobId: string };

    // Delete it
    const deleteResult = await cronDeleteTool.handler({ id: jobId }, ctx);
    const parsed = JSON.parse(deleteResult);
    expect(parsed.message).toContain('cancelled');

    // Deleting again should fail
    const deleteAgain = await cronDeleteTool.handler({ id: jobId }, ctx);
    const parsed2 = JSON.parse(deleteAgain);
    expect(parsed2.error).toContain('not found');
  });

  it('schedule_wakeup schema has correct format', () => {
    expect(scheduleWakeupTool.name).toBe('schedule_wakeup');
    expect(scheduleWakeupTool.schema.type).toBe('function');
  });

  it('schedule_wakeup creates a one-shot delayed job', async () => {
    const result = await scheduleWakeupTool.handler(
      { delaySeconds: 300, reason: 'Wait for CI', prompt: 'Check CI status' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.wakeupId).toMatch(/^cron_\d+$/);
    expect(parsed.delaySeconds).toBe(300);
    expect(parsed.reason).toBe('Wait for CI');
    expect(parsed.fireAt).toBeDefined();
  });

  it('schedule_wakeup clamps delay to [60, 3600]', async () => {
    // Too low → clamped to 60
    const r1 = await scheduleWakeupTool.handler(
      { delaySeconds: 1, reason: 'Min clamp test', prompt: 'x' },
      ctx,
    );
    expect(JSON.parse(r1).delaySeconds).toBe(60);

    // Too high → clamped to 3600
    const r2 = await scheduleWakeupTool.handler(
      { delaySeconds: 99999, reason: 'Max clamp test', prompt: 'x' },
      ctx,
    );
    expect(JSON.parse(r2).delaySeconds).toBe(3600);
  });
});

// ============================================================================
// Web search tool (updated — real implementation with env var fallback)
// ============================================================================

describe('web_search tool', () => {
  it('returns error about configuration when env vars are not set', async () => {
    const result = await webSearchTool.handler({ query: 'test' }, ctx);
    const parsed = JSON.parse(result);
    // Either succeeds via env or reports missing config
    if (parsed.error) {
      expect(parsed.error).toMatch(/API key|configuration/i);
    }
  });

  it('has correct tool metadata', () => {
    expect(webSearchTool.name).toBe('web_search');
    expect(webSearchTool.toolset).toBe('web');
    expect(webSearchTool.isAsync).toBe(true);
  });
});

// ============================================================================
// Web fetch tool (updated — real implementation)
// ============================================================================

describe('web_fetch tool', () => {
  it('returns error for invalid URL', async () => {
    const result = await webFetchTool.handler({ url: 'not-a-url', prompt: 'test' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Invalid URL');
  });

  it('returns error for unsupported protocol', async () => {
    const result = await webFetchTool.handler({ url: 'ftp://example.com/file', prompt: 'test' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Unsupported protocol');
  });

  it('returns error when prompt is missing', async () => {
    const result = await webFetchTool.handler({ url: 'http://example.com' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Missing required');
  });

  it('has correct tool metadata', () => {
    expect(webFetchTool.name).toBe('web_fetch');
    expect(webFetchTool.toolset).toBe('web');
    expect(webFetchTool.isAsync).toBe(true);
  });

  it('can fetch a real URL', async () => {
    const result = await webFetchTool.handler(
      { url: 'https://httpbin.org/status/200', prompt: 'test fetch' },
      ctx,
    );
    const parsed = JSON.parse(result);
    // httpbin.org might not be reachable in all environments, so accept either
    if (parsed.error) {
      expect(parsed.error).toMatch(/fetch|HTTP|timeout|network/i);
    } else {
      expect(parsed.url).toBe('https://httpbin.org/status/200');
    }
  }, 15000);
});

// ============================================================================
// Worktree tools — enter_worktree, exit_worktree
// ============================================================================

describe('worktree tools', () => {
  let tmpDir: string;

  beforeAll(() => {
    tmpDir = mkdtempSync(join(tmpdir(), 'jarvis-wt-'));
  });

  afterAll(() => {
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch { /* ignore */ }
  });

  it('enter_worktree schema has correct format', () => {
    expect(enterWorktreeTool.name).toBe('enter_worktree');
    expect(enterWorktreeTool.schema.type).toBe('function');
  });

  it('exit_worktree schema has correct format', () => {
    expect(exitWorktreeTool.name).toBe('exit_worktree');
    expect(exitWorktreeTool.schema.type).toBe('function');
  });

  it('enter_worktree returns error when not in a git repo', async () => {
    // Change to a non-git temp dir
    const origCwd = process.cwd();
    try {
      process.chdir(tmpDir);
      const result = await enterWorktreeTool.handler({}, ctx);
      const parsed = JSON.parse(result);
      expect(parsed.error).toContain('Not in a git repository');
    } finally {
      process.chdir(origCwd);
    }
  });

  it('enter_worktree returns error for invalid name', async () => {
    const result = await enterWorktreeTool.handler(
      { name: 'name with spaces!' },
      ctx,
    );
    const parsed = JSON.parse(result);
    if (!parsed.error?.includes('Not in a git repository')) {
      expect(parsed.error).toContain('Invalid worktree name');
    }
  });

  it('exit_worktree returns error when worktree_path is missing', async () => {
    const result = await exitWorktreeTool.handler({ action: 'keep' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Missing required');
  });

  it('exit_worktree returns error for nonexistent path', async () => {
    const result = await exitWorktreeTool.handler(
      { action: 'keep', worktree_path: join(tmpDir, 'nonexistent') },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('does not exist');
  });
});

// ============================================================================
// Agent tool (factory — tested with mock pool)
// ============================================================================

describe('Agent tool', () => {
  it('creates a functioning agent tool with mock pool', async () => {
    const mockPool: AgentPool = {
      submit(config) {
        const agentId = config.agentId;
        let resolveCompletion!: (result: { agentId: string; status: string; answer?: string; error?: string; turnsUsed?: number }) => void;
        const completion = new Promise<{ agentId: string; status: string; answer?: string; error?: string; turnsUsed?: number }>((resolve) => {
          resolveCompletion = resolve;
        });

        // Resolve immediately for foreground test
        setTimeout(() => {
          resolveCompletion({ agentId, status: 'completed', answer: 'Task done: ' + config.task, turnsUsed: 3 });
        }, 10);

        return { agentId, status: 'running', completion, cancel: () => {} };
      },
    };

    const agentTool = createAgentTool(mockPool);
    expect(agentTool.name).toBe('Agent');
    expect(agentTool.schema.type).toBe('function');
    expect(agentTool.isAsync).toBe(true);

    // Test foreground execution
    const result = await agentTool.handler(
      { description: 'Test task', prompt: 'Do something useful', subagent_type: 'explore' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.agentId).toMatch(/^agent_/);
    expect(parsed.status).toBe('completed');
    expect(parsed.answer).toContain('Do something useful');
    expect(parsed.turnsUsed).toBe(3);
  });

  it('returns error for missing parameters', async () => {
    const mockPool: AgentPool = {
      submit: () => { throw new Error('should not be called'); },
    };
    const agentTool = createAgentTool(mockPool);

    const result = await agentTool.handler({}, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Missing required');
  });

  it('returns error on pool failure', async () => {
    const mockPool: AgentPool = {
      submit: () => { throw new Error('Pool exhausted'); },
    };
    const agentTool = createAgentTool(mockPool);

    const result = await agentTool.handler(
      { description: 'Failing task', prompt: 'Will fail' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Pool exhausted');
  });

  it('supports background mode', async () => {
    const mockPool: AgentPool = {
      submit(config) {
        const agentId = config.agentId;
        let resolveCompletion!: (result: { agentId: string; status: string; answer?: string }) => void;
        const completion = new Promise<{ agentId: string; status: string; answer?: string }>((resolve) => {
          resolveCompletion = resolve;
        });
        // Don't resolve in background mode
        return { agentId, status: 'pending', completion, cancel: () => {} };
      },
    };
    const agentTool = createAgentTool(mockPool);

    const result = await agentTool.handler(
      { description: 'Bg task', prompt: 'Run forever', run_in_background: true },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.agentId).toMatch(/^agent_/);
    expect(parsed.message).toContain('started in background');
  });
});

// ============================================================================
// MCP resource tools (factory — tested with mock client)
// ============================================================================

describe('MCP resource tools', () => {
  const mockClient: McpResourceClient = {
    connections: [
      {
        serverInfo: { name: 'test-server', version: '1.0' },
        resources: [
          { uri: 'file:///data/schema.sql', name: 'schema.sql', description: 'Database schema', mimeType: 'text/sql', server: 'test-server' },
          { uri: 'file:///data/config.json', name: 'config.json', description: 'Configuration', mimeType: 'application/json', server: 'test-server' },
        ],
      },
      {
        serverInfo: { name: 'docs-server', version: '0.5' },
        resources: [
          { uri: 'doc://readme', name: 'README', description: 'Documentation index', mimeType: 'text/markdown', server: 'docs-server' },
        ],
      },
    ],
    async readResource(connection, uri) {
      if (uri === 'file:///data/schema.sql') {
        return { text: 'CREATE TABLE users (id INT PRIMARY KEY);' };
      }
      throw new Error('Resource not found');
    },
  };

  it('list_mcp_resources lists all resources', async () => {
    const tool = createListMcpResourcesTool(mockClient);
    expect(tool.name).toBe('list_mcp_resources');

    const result = await tool.handler({}, ctx);
    const parsed = JSON.parse(result);
    expect(Array.isArray(parsed.resources)).toBe(true);
    expect(parsed.resources).toHaveLength(3);
    expect(parsed.resources[0].server).toBe('test-server');
    expect(parsed.resources[0].uri).toBe('file:///data/schema.sql');
  });

  it('list_mcp_resources filters by server', async () => {
    const tool = createListMcpResourcesTool(mockClient);
    const result = await tool.handler({ server: 'docs-server' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.resources).toHaveLength(1);
    expect(parsed.resources[0].name).toBe('README');
  });

  it('list_mcp_resources returns message when no resources match', async () => {
    const tool = createListMcpResourcesTool(mockClient);
    const result = await tool.handler({ server: 'nonexistent-server' }, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.resources).toHaveLength(0);
    expect(parsed.message).toBeDefined();
  });

  it('read_mcp_resource reads a resource by server + URI', async () => {
    const tool = createReadMcpResourceTool(mockClient);
    expect(tool.name).toBe('read_mcp_resource');

    const result = await tool.handler(
      { server: 'test-server', uri: 'file:///data/schema.sql' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.server).toBe('test-server');
    expect(parsed.uri).toBe('file:///data/schema.sql');
    expect(parsed.content).toBeDefined();
  });

  it('read_mcp_resource returns error for unknown server', async () => {
    const tool = createReadMcpResourceTool(mockClient);
    const result = await tool.handler(
      { server: 'no-such-server', uri: 'any://uri' },
      ctx,
    );
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('not found');
  });

  it('read_mcp_resource returns error for missing parameters', async () => {
    const tool = createReadMcpResourceTool(mockClient);
    const result = await tool.handler({}, ctx);
    const parsed = JSON.parse(result);
    expect(parsed.error).toContain('Missing required');
  });
});

// ============================================================================
// Tool schema routing accuracy — verify all tool schemas are well-formed
// and have unambiguous names/descriptions for natural language dispatch
// ============================================================================

describe('tool schema routing readiness', () => {
  const allTools = [
    bashTool, readFileTool, writeFileTool, editFileTool, globTool, grepTool,
    webSearchTool, webFetchTool, askUserQuestionTool,
    taskCreateTool, taskUpdateTool, taskListTool, taskGetTool,
    enterPlanModeTool, exitPlanModeTool, notebookEditTool,
    cronCreateTool, cronDeleteTool, cronListTool, scheduleWakeupTool,
    enterWorktreeTool, exitWorktreeTool,
  ];

  it('all tools have unique names', () => {
    const names = allTools.map((t) => t.name);
    const unique = new Set(names);
    expect(unique.size).toBe(names.length);
  });

  it('all tools have their name in the schema function name', () => {
    for (const tool of allTools) {
      const fn = tool.schema.function as Record<string, unknown>;
      expect(fn.name).toBe(tool.name);
    }
  });

  it('all tools have non-empty descriptions', () => {
    for (const tool of allTools) {
      const fn = tool.schema.function as Record<string, unknown>;
      const desc = String(fn.description ?? '');
      expect(desc.length).toBeGreaterThan(10);
    }
  });

  it('tool descriptions contain key distinguishing terms', () => {
    // Each tool should have description terms that uniquely identify it
    const descChecks: Array<[string, string]> = [
      ['bash', 'shell command'],
      ['read_file', 'file'],
      ['write_file', 'write'],
      ['edit_file', 'replace'],
      ['glob', 'glob pattern'],
      ['grep', 'search'],
      ['web_search', 'search the web'],
      ['web_fetch', 'fetch'],
      ['task_create', 'create'],
      ['task_update', 'update'],
      ['task_list', 'list'],
      ['task_get', 'retrieve'],
      ['cron_create', 'schedule'],
      ['schedule_wakeup', 'wakeup'],
      ['enter_worktree', 'worktree'],
    ];

    for (const [name, expectedTerm] of descChecks) {
      const tool = allTools.find((t) => t.name === name);
      if (!tool) continue;
      const fn = tool.schema.function as Record<string, unknown>;
      const desc = String(fn.description ?? '').toLowerCase();
      expect(desc).toContain(expectedTerm.toLowerCase());
    }
  });

  it('all tools have schema type "function"', () => {
    for (const tool of allTools) {
      expect(tool.schema.type).toBe('function');
    }
  });

  it('all tools with isAsync flag are known async-capable tools', () => {
    const asyncTools = allTools.filter((t) => t.isAsync);
    const knownAsync = new Set([
      'bash', 'read_file', 'write_file', 'edit_file', 'glob', 'grep',
      'web_search', 'web_fetch', 'ask_user_question', 'notebook_edit',
      'enter_worktree', 'exit_worktree',
    ]);
    for (const tool of asyncTools) {
      expect(knownAsync.has(tool.name)).toBe(true);
    }
  });
});
