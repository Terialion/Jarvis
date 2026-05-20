# Diff Display & Plugin Packaging — Design Spec

## A. Diff Display

### Problem
Jarvis generates unified diffs via `render_diff()` (Python/Rich) but the Ink/React TUI never renders them. Users only see file names, not actual code changes. Claude Code and Codex both show syntax-highlighted diffs inline after every file edit.

### Reference implementations

**Codex `diff_render.rs` (2482 lines):**
- `FileChange` enum: `Add {content}`, `Delete {content}`, `Update {unified_diff}`
- Dark theme: add bg `#213A2B`, del bg `#4A221D`; Light theme: add bg `#dafbe1`, del bg `#ffebe9`
- 3-column layout: `gutter(line#) │ sign(+/-) │ content(syntax-highlighted)`
- Three display contexts: inline chat, approval overlay, scrollable diff view

**Claude Code SDK:**
- `FileEditOutput` / `FileWriteOutput` carry `structuredPatch` (hunks) + `gitDiff` (unified patch + diffstat)
- CSS: `.hljs-deletion` (red bg), `.hljs-addition` (green bg)

### Design

**Data flow:**
1. `file_editor.replace_text` / `write_file` / `insert_text` executes → auto-runs `FileEditor.diff()`
2. `AgentLoop` emits new `ModelChunk(kind="file_change")` with structured diff data
3. Bridge forwards as JSON to TUI
4. TUI renders `DiffBlock` component inline in MessageList

**New protocol type — `FileChange`:**
```
path: string
diff_text: string
added: number
removed: number
status: "created" | "modified" | "deleted"
```

**New TUI component — `DiffBlock`:**
- 3-column layout: line# │ +/- │ content
- Colors: green for additions, red for deletions
- Collapsible when >20 lines (default collapsed, show first 10)
- Expand/collapse with Enter

**`/diff` command enhancement:**
- Currently shows file list only → show full `render_diff()` output

---

## B. Plugin Packaging

### Problem
Jarvis has a mature skill system (`SkillRegistry`, `SkillSpec`, `SkillLoader`) but no plugin-level packaging standard. Skills live in loose directories with no manifest, no component discovery, no versioning.

### Reference: Claude Code plugin.json

```
plugin-name/
├── .claude-plugin/
│   └── plugin.json          # ONLY required file
├── commands/                # Slash commands (markdown + YAML frontmatter)
├── agents/                  # Agent definitions
├── skills/                  # SKILL.md files
├── hooks/                   # hooks.json
└── .mcp.json               # MCP server config
```

`plugin.json` minimal format: `{ "name": "my-plugin" }`

### Design

**New module: `src/jarvis/core/plugins/`**

**Plugin discovery — 3 scopes (priority order):**
1. `<project>/.claude-plugin/plugin.json`
2. `~/.jarvis/plugins/<name>/plugin.json`
3. `$JARVIS_PLUGIN_DIRS` (colon-separated)

**Component auto-registration on plugin load:**
- `commands/` *.md → register as slash command handlers
- `agents/` *.md → register as available agent types
- `skills/` → append to SkillRegistry
- `hooks/hooks.json` → register in HookRegistry
- `.mcp.json` → register MCP server connections

**MCP integration:** Parse `.mcp.json`, manage server subprocess lifecycle, `${PLUGIN_ROOT}` variable substitution.
