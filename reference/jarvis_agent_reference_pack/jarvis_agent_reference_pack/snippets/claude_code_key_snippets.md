# Claude Code 关键参考摘录

### 严格权限配置

Source: `claude-code/claude-code-main/examples/settings/settings-strict.json` lines 1-40

```
0001: {
0002:   "permissions": {
0003:     "disableBypassPermissionsMode": "disable",
0004:     "ask": [
0005:       "Bash"
0006:     ],
0007:     "deny": [
0008:       "WebSearch",
0009:       "WebFetch"
0010:     ]
0011:   },
0012:   "allowManagedPermissionRulesOnly": true,
0013:   "allowManagedHooksOnly": true,
0014:   "strictKnownMarketplaces": [],
0015:   "sandbox": {
0016:     "autoAllowBashIfSandboxed": false,
0017:     "excludedCommands": [],
0018:     "network": {
0019:       "allowUnixSockets": [],
0020:       "allowAllUnixSockets": false,
0021:       "allowLocalBinding": false,
0022:       "allowedDomains": [],
0023:       "httpProxyPort": null,
0024:       "socksProxyPort": null
0025:     },
0026:     "enableWeakerNestedSandbox": false
0027:   }
0028: }
```
### PreToolUse Bash validator hook

Source: `claude-code/claude-code-main/examples/hooks/bash_command_validator_example.py` lines 1-75

```
0001: #!/usr/bin/env python3
0002: """
0003: Claude Code Hook: Bash Command Validator
0004: =========================================
0005: This hook runs as a PreToolUse hook for the Bash tool.
0006: It validates bash commands against a set of rules before execution.
0007: In this case it changes grep calls to using rg.
0008: 
0009: Read more about hooks here: https://docs.anthropic.com/en/docs/claude-code/hooks
0010: 
0011: Make sure to change your path to your actual script.
0012: 
0013: {
0014:   "hooks": {
0015:     "PreToolUse": [
0016:       {
0017:         "matcher": "Bash",
0018:         "hooks": [
0019:           {
0020:             "type": "command",
0021:             "command": "python3 /path/to/claude-code/examples/hooks/bash_command_validator_example.py"
0022:           }
0023:         ]
0024:       }
0025:     ]
0026:   }
0027: }
0028: 
0029: """
0030: 
0031: import json
0032: import re
0033: import sys
0034: 
0035: # Define validation rules as a list of (regex pattern, message) tuples
0036: _VALIDATION_RULES = [
0037:     (
0038:         r"^grep\b(?!.*\|)",
0039:         "Use 'rg' (ripgrep) instead of 'grep' for better performance and features",
0040:     ),
0041:     (
0042:         r"^find\s+\S+\s+-name\b",
0043:         "Use 'rg --files | rg pattern' or 'rg --files -g pattern' instead of 'find -name' for better performance",
0044:     ),
0045: ]
0046: 
0047: 
0048: def _validate_command(command: str) -> list[str]:
0049:     issues = []
0050:     for pattern, message in _VALIDATION_RULES:
0051:         if re.search(pattern, command):
0052:             issues.append(message)
0053:     return issues
0054: 
0055: 
0056: def main():
0057:     try:
0058:         input_data = json.load(sys.stdin)
0059:     except json.JSONDecodeError as e:
0060:         print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
0061:         # Exit code 1 shows stderr to the user but not to Claude
0062:         sys.exit(1)
0063: 
0064:     tool_name = input_data.get("tool_name", "")
0065:     if tool_name != "Bash":
0066:         sys.exit(0)
0067: 
0068:     tool_input = input_data.get("tool_input", {})
0069:     command = tool_input.get("command", "")
0070: 
0071:     if not command:
0072:         sys.exit(0)
0073: 
0074:     issues = _validate_command(command)
0075:     if issues:
```
### Hook Development skill

Source: `claude-code/claude-code-main/plugins/plugin-dev/skills/hook-development/SKILL.md` lines 1-80

```
0001: ---
0002: name: Hook Development
0003: description: This skill should be used when the user asks to "create a hook", "add a PreToolUse/PostToolUse/Stop hook", "validate tool use", "implement prompt-based hooks", "use ${CLAUDE_PLUGIN_ROOT}", "set up event-driven automation", "block dangerous commands", or mentions hook events (PreToolUse, PostToolUse, Stop, SubagentStop, SessionStart, SessionEnd, UserPromptSubmit, PreCompact, Notification). Provides comprehensive guidance for creating and implementing Claude Code plugin hooks with focus on advanced prompt-based hooks API.
0004: version: 0.1.0
0005: ---
0006: 
0007: # Hook Development for Claude Code Plugins
0008: 
0009: ## Overview
0010: 
0011: Hooks are event-driven automation scripts that execute in response to Claude Code events. Use hooks to validate operations, enforce policies, add context, and integrate external tools into workflows.
0012: 
0013: **Key capabilities:**
0014: - Validate tool calls before execution (PreToolUse)
0015: - React to tool results (PostToolUse)
0016: - Enforce completion standards (Stop, SubagentStop)
0017: - Load project context (SessionStart)
0018: - Automate workflows across the development lifecycle
0019: 
0020: ## Hook Types
0021: 
0022: ### Prompt-Based Hooks (Recommended)
0023: 
0024: Use LLM-driven decision making for context-aware validation:
0025: 
0026: ```json
0027: {
0028:   "type": "prompt",
0029:   "prompt": "Evaluate if this tool use is appropriate: $TOOL_INPUT",
0030:   "timeout": 30
0031: }
0032: ```
0033: 
0034: **Supported events:** Stop, SubagentStop, UserPromptSubmit, PreToolUse
0035: 
0036: **Benefits:**
0037: - Context-aware decisions based on natural language reasoning
0038: - Flexible evaluation logic without bash scripting
0039: - Better edge case handling
0040: - Easier to maintain and extend
0041: 
0042: ### Command Hooks
0043: 
0044: Execute bash commands for deterministic checks:
0045: 
0046: ```json
0047: {
0048:   "type": "command",
0049:   "command": "bash ${CLAUDE_PLUGIN_ROOT}/scripts/validate.sh",
0050:   "timeout": 60
0051: }
0052: ```
0053: 
0054: **Use for:**
0055: - Fast deterministic validations
0056: - File system operations
0057: - External tool integrations
0058: - Performance-critical checks
0059: 
0060: ## Hook Configuration Formats
0061: 
0062: ### Plugin hooks.json Format
0063: 
0064: **For plugin hooks** in `hooks/hooks.json`, use wrapper format:
0065: 
0066: ```json
0067: {
0068:   "description": "Brief explanation of hooks (optional)",
0069:   "hooks": {
0070:     "PreToolUse": [...],
0071:     "Stop": [...],
0072:     "SessionStart": [...]
0073:   }
0074: }
0075: ```
0076: 
0077: **Key points:**
0078: - `description` field is optional
0079: - `hooks` field is required wrapper containing actual hook events
0080: - This is the **plugin-specific format**
```
### Skill Development skill

Source: `claude-code/claude-code-main/plugins/plugin-dev/skills/skill-development/SKILL.md` lines 1-85

```
0001: ---
0002: name: Skill Development
0003: description: This skill should be used when the user wants to "create a skill", "add a skill to plugin", "write a new skill", "improve skill description", "organize skill content", or needs guidance on skill structure, progressive disclosure, or skill development best practices for Claude Code plugins.
0004: version: 0.1.0
0005: ---
0006: 
0007: # Skill Development for Claude Code Plugins
0008: 
0009: This skill provides guidance for creating effective skills for Claude Code plugins.
0010: 
0011: ## About Skills
0012: 
0013: Skills are modular, self-contained packages that extend Claude's capabilities by providing
0014: specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
0015: domains or tasks—they transform Claude from a general-purpose agent into a specialized agent
0016: equipped with procedural knowledge that no model can fully possess.
0017: 
0018: ### What Skills Provide
0019: 
0020: 1. Specialized workflows - Multi-step procedures for specific domains
0021: 2. Tool integrations - Instructions for working with specific file formats or APIs
0022: 3. Domain expertise - Company-specific knowledge, schemas, business logic
0023: 4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks
0024: 
0025: ### Anatomy of a Skill
0026: 
0027: Every skill consists of a required SKILL.md file and optional bundled resources:
0028: 
0029: ```
0030: skill-name/
0031: ├── SKILL.md (required)
0032: │   ├── YAML frontmatter metadata (required)
0033: │   │   ├── name: (required)
0034: │   │   └── description: (required)
0035: │   └── Markdown instructions (required)
0036: └── Bundled Resources (optional)
0037:     ├── scripts/          - Executable code (Python/Bash/etc.)
0038:     ├── references/       - Documentation intended to be loaded into context as needed
0039:     └── assets/           - Files used in output (templates, icons, fonts, etc.)
0040: ```
0041: 
0042: #### SKILL.md (required)
0043: 
0044: **Metadata Quality:** The `name` and `description` in YAML frontmatter determine when Claude will use the skill. Be specific about what the skill does and when to use it. Use the third-person (e.g. "This skill should be used when..." instead of "Use this skill when...").
0045: 
0046: #### Bundled Resources (optional)
0047: 
0048: ##### Scripts (`scripts/`)
0049: 
0050: Executable code (Python/Bash/etc.) for tasks that require deterministic reliability or are repeatedly rewritten.
0051: 
0052: - **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
0053: - **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
0054: - **Benefits**: Token efficient, deterministic, may be executed without loading into context
0055: - **Note**: Scripts may still need to be read by Claude for patching or environment-specific adjustments
0056: 
0057: ##### References (`references/`)
0058: 
0059: Documentation and reference material intended to be loaded as needed into context to inform Claude's process and thinking.
0060: 
0061: - **When to include**: For documentation that Claude should reference while working
0062: - **Examples**: `references/finance.md` for financial schemas, `references/mnda.md` for company NDA template, `references/policies.md` for company policies, `references/api_docs.md` for API specifications
0063: - **Use cases**: Database schemas, API documentation, domain knowledge, company policies, detailed workflow guides
0064: - **Benefits**: Keeps SKILL.md lean, loaded only when Claude determines it's needed
0065: - **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
0066: - **Avoid duplication**: Information should live in either SKILL.md or references files, not both. Prefer references files for detailed information unless it's truly core to the skill—this keeps SKILL.md lean while making information discoverable without hogging the context window. Keep only essential procedural instructions and workflow guidance in SKILL.md; move detailed reference material, schemas, and examples to references files.
0067: 
0068: ##### Assets (`assets/`)
0069: 
0070: Files not intended to be loaded into context, but rather used within the output Claude produces.
0071: 
0072: - **When to include**: When the skill needs files that will be used in the final output
0073: - **Examples**: `assets/logo.png` for brand assets, `assets/slides.pptx` for PowerPoint templates, `assets/frontend-template/` for HTML/React boilerplate, `assets/font.ttf` for typography
0074: - **Use cases**: Templates, images, icons, boilerplate code, fonts, sample documents that get copied or modified
0075: - **Benefits**: Separates output resources from documentation, enables Claude to use files without loading them into context
0076: 
0077: ### Progressive Disclosure Design Principle
0078: 
0079: Skills use a three-level loading system to manage context efficiently:
0080: 
0081: 1. **Metadata (name + description)** - Always in context (~100 words)
0082: 2. **SKILL.md body** - When skill triggers (<5k words)
0083: 3. **Bundled resources** - As needed by Claude (Unlimited*)
0084: 
0085: *Unlimited because scripts can be executed without reading into context window.
```
### 命令 frontmatter allowed-tools

Source: `claude-code/claude-code-main/plugins/commit-commands/commands/commit.md` lines 1-35

```
0001: ---
0002: allowed-tools: Bash(git add:*), Bash(git status:*), Bash(git commit:*)
0003: description: Create a git commit
0004: ---
0005: 
0006: ## Context
0007: 
0008: - Current git status: !`git status`
0009: - Current git diff (staged and unstaged changes): !`git diff HEAD`
0010: - Current branch: !`git branch --show-current`
0011: - Recent commits: !`git log --oneline -10`
0012: 
0013: ## Your task
0014: 
0015: Based on the above changes, create a single git commit.
0016: 
0017: You have the capability to call multiple tools in a single response. Stage and create the commit using a single message. Do not use any other tools or do anything else. Do not send any other text or messages besides these tool calls.
```
