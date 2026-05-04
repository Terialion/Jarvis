# OpenClaw 关键参考摘录

### Agent loop 生命周期

Source: `openclaw/openclaw-main/docs/concepts/agent-loop.md` lines 1-75

```
0001: ---
0002: summary: "Agent loop lifecycle, streams, and wait semantics"
0003: read_when:
0004:   - You need an exact walkthrough of the agent loop or lifecycle events
0005:   - You are changing session queueing, transcript writes, or session write lock behavior
0006: title: "Agent loop"
0007: ---
0008: 
0009: An agentic loop is the full “real” run of an agent: intake → context assembly → model inference →
0010: tool execution → streaming replies → persistence. It’s the authoritative path that turns a message
0011: into actions and a final reply, while keeping session state consistent.
0012: 
0013: In OpenClaw, a loop is a single, serialized run per session that emits lifecycle and stream events
0014: as the model thinks, calls tools, and streams output. This doc explains how that authentic loop is
0015: wired end-to-end.
0016: 
0017: ## Entry points
0018: 
0019: - Gateway RPC: `agent` and `agent.wait`.
0020: - CLI: `agent` command.
0021: 
0022: ## How it works (high-level)
0023: 
0024: 1. `agent` RPC validates params, resolves session (sessionKey/sessionId), persists session metadata, returns `{ runId, acceptedAt }` immediately.
0025: 2. `agentCommand` runs the agent:
0026:    - resolves model + thinking/verbose/trace defaults
0027:    - loads skills snapshot
0028:    - calls `runEmbeddedPiAgent` (pi-agent-core runtime)
0029:    - emits **lifecycle end/error** if the embedded loop does not emit one
0030: 3. `runEmbeddedPiAgent`:
0031:    - serializes runs via per-session + global queues
0032:    - resolves model + auth profile and builds the pi session
0033:    - subscribes to pi events and streams assistant/tool deltas
0034:    - enforces timeout -> aborts run if exceeded
0035:    - returns payloads + usage metadata
0036: 4. `subscribeEmbeddedPiSession` bridges pi-agent-core events to OpenClaw `agent` stream:
0037:    - tool events => `stream: "tool"`
0038:    - assistant deltas => `stream: "assistant"`
0039:    - lifecycle events => `stream: "lifecycle"` (`phase: "start" | "end" | "error"`)
0040: 5. `agent.wait` uses `waitForAgentRun`:
0041:    - waits for **lifecycle end/error** for `runId`
0042:    - returns `{ status: ok|error|timeout, startedAt, endedAt, error? }`
0043: 
0044: ## Queueing + concurrency
0045: 
0046: - Runs are serialized per session key (session lane) and optionally through a global lane.
0047: - This prevents tool/session races and keeps session history consistent.
0048: - Messaging channels can choose queue modes (collect/steer/followup) that feed this lane system.
0049:   See [Command Queue](/concepts/queue).
0050: - Transcript writes are also protected by a session write lock on the session file. The lock is
0051:   process-aware and file-based, so it catches writers that bypass the in-process queue or come from
0052:   another process.
0053: - Session write locks are non-reentrant by default. If a helper intentionally nests acquisition of
0054:   the same lock while preserving one logical writer, it must opt in explicitly with
0055:   `allowReentrant: true`.
0056: 
0057: ## Session + workspace preparation
0058: 
0059: - Workspace is resolved and created; sandboxed runs may redirect to a sandbox workspace root.
0060: - Skills are loaded (or reused from a snapshot) and injected into env and prompt.
0061: - Bootstrap/context files are resolved and injected into the system prompt report.
0062: - A session write lock is acquired; `SessionManager` is opened and prepared before streaming. Any
0063:   later transcript rewrite, compaction, or truncation path must take the same lock before opening or
0064:   mutating the transcript file.
0065: 
0066: ## Prompt assembly + system prompt
0067: 
0068: - System prompt is built from OpenClaw’s base prompt, skills prompt, bootstrap context, and per-run overrides.
0069: - Model-specific limits and compaction reserve tokens are enforced.
0070: - See [System prompt](/concepts/system-prompt) for what the model sees.
0071: 
0072: ## Hook points (where you can intercept)
0073: 
0074: OpenClaw has two hook systems:
0075: 
```
### Session queue 串行化

Source: `openclaw/openclaw-main/docs/concepts/queue.md` lines 1-70

```
0001: ---
0002: summary: "Auto-reply queue modes, defaults, and per-session overrides"
0003: read_when:
0004:   - Changing auto-reply execution or concurrency
0005:   - Explaining /queue modes or message steering behavior
0006: title: "Command queue"
0007: ---
0008: 
0009: We serialize inbound auto-reply runs (all channels) through a tiny in-process queue to prevent multiple agent runs from colliding, while still allowing safe parallelism across sessions.
0010: 
0011: ## Why
0012: 
0013: - Auto-reply runs can be expensive (LLM calls) and can collide when multiple inbound messages arrive close together.
0014: - Serializing avoids competing for shared resources (session files, logs, CLI stdin) and reduces the chance of upstream rate limits.
0015: 
0016: ## How it works
0017: 
0018: - A lane-aware FIFO queue drains each lane with a configurable concurrency cap (default 1 for unconfigured lanes; main defaults to 4, subagent to 8).
0019: - `runEmbeddedPiAgent` enqueues by **session key** (lane `session:<key>`) to guarantee only one active run per session.
0020: - Each session run is then queued into a **global lane** (`main` by default) so overall parallelism is capped by `agents.defaults.maxConcurrent`.
0021: - When verbose logging is enabled, queued runs emit a short notice if they waited more than ~2s before starting.
0022: - Typing indicators still fire immediately on enqueue (when supported by the channel) so user experience is unchanged while we wait our turn.
0023: 
0024: ## Defaults
0025: 
0026: When unset, all inbound channel surfaces use:
0027: 
0028: - `mode: "steer"`
0029: - `debounceMs: 500`
0030: - `cap: 20`
0031: - `drop: "summarize"`
0032: 
0033: `steer` is the default because it keeps the active model turn responsive without
0034: starting a second session run. It drains all steering messages that arrived
0035: before the next model boundary. If the current run cannot accept steering,
0036: OpenClaw falls back to a followup queue entry.
0037: 
0038: ## Queue modes
0039: 
0040: Inbound messages can steer the current run, wait for a followup turn, or do both:
0041: 
0042: - `steer`: queue steering messages into the active runtime. Pi delivers all pending steering messages **after the current assistant turn finishes executing its tool calls**, before the next LLM call; Codex app-server receives one batched `turn/steer`. If the run is not actively streaming or steering is unavailable, OpenClaw falls back to a followup queue entry.
0043: - `queue` (legacy): old one-at-a-time steering. Pi delivers one queued steering message at each model boundary; Codex app-server receives separate `turn/steer` requests. Prefer `steer` unless you need the previous serialized behavior.
0044: - `followup`: enqueue each message for a later agent turn after the current run ends.
0045: - `collect`: coalesce queued messages into a **single** followup turn after the quiet window. If messages target different channels/threads, they drain individually to preserve routing.
0046: - `steer-backlog` (aka `steer+backlog`): steer now **and** preserve the same message for a followup turn.
0047: - `interrupt` (legacy): abort the active run for that session, then run the newest message.
0048: 
0049: Steer-backlog means you can get a followup response after the steered run, so
0050: streaming surfaces can look like duplicates. Prefer `collect`/`steer` if you want
0051: one response per inbound message.
0052: 
0053: For runtime-specific timing and dependency behavior, see
0054: [Steering queue](/concepts/queue-steering).
0055: 
0056: Configure globally or per channel via `messages.queue`:
0057: 
0058: ```json5
0059: {
0060:   messages: {
0061:     queue: {
0062:       mode: "steer",
0063:       debounceMs: 500,
0064:       cap: 20,
0065:       drop: "summarize",
0066:       byChannel: { discord: "collect" },
0067:     },
0068:   },
0069: }
0070: ```
```
### Inbound message 到 reply

Source: `openclaw/openclaw-main/docs/concepts/messages.md` lines 1-80

```
0001: ---
0002: summary: "Message flow, sessions, queueing, and reasoning visibility"
0003: read_when:
0004:   - Explaining how inbound messages become replies
0005:   - Clarifying sessions, queueing modes, or streaming behavior
0006:   - Documenting reasoning visibility and usage implications
0007: title: "Messages"
0008: ---
0009: 
0010: OpenClaw handles inbound messages through a pipeline of session resolution, queueing, streaming, tool execution, and reasoning visibility. This page maps the path from inbound message to reply.
0011: 
0012: ## Message flow (high level)
0013: 
0014: ```
0015: Inbound message
0016:   -> routing/bindings -> session key
0017:   -> queue (if a run is active)
0018:   -> agent run (streaming + tools)
0019:   -> outbound replies (channel limits + chunking)
0020: ```
0021: 
0022: Key knobs live in configuration:
0023: 
0024: - `messages.*` for prefixes, queueing, and group behavior.
0025: - `agents.defaults.*` for block streaming and chunking defaults.
0026: - Channel overrides (`channels.whatsapp.*`, `channels.telegram.*`, etc.) for caps and streaming toggles.
0027: 
0028: See [Configuration](/gateway/configuration) for full schema.
0029: 
0030: ## Inbound dedupe
0031: 
0032: Channels can redeliver the same message after reconnects. OpenClaw keeps a
0033: short-lived cache keyed by channel/account/peer/session/message id so duplicate
0034: deliveries do not trigger another agent run.
0035: 
0036: ## Inbound debouncing
0037: 
0038: Rapid consecutive messages from the **same sender** can be batched into a single
0039: agent turn via `messages.inbound`. Debouncing is scoped per channel + conversation
0040: and uses the most recent message for reply threading/IDs.
0041: 
0042: Config (global default + per-channel overrides):
0043: 
0044: ```json5
0045: {
0046:   messages: {
0047:     inbound: {
0048:       debounceMs: 2000,
0049:       byChannel: {
0050:         whatsapp: 5000,
0051:         slack: 1500,
0052:         discord: 1500,
0053:       },
0054:     },
0055:   },
0056: }
0057: ```
0058: 
0059: Notes:
0060: 
0061: - Debounce applies to **text-only** messages; media/attachments flush immediately.
0062: - Control commands bypass debouncing so they remain standalone — **except** when a channel explicitly opts in to same-sender DM coalescing (e.g. [BlueBubbles `coalesceSameSenderDms`](/channels/bluebubbles#coalescing-split-send-dms-command--url-in-one-composition)), where DM commands wait inside the debounce window so a split-send payload can join the same agent turn.
0063: 
0064: ## Sessions and devices
0065: 
0066: Sessions are owned by the gateway, not by clients.
0067: 
0068: - Direct chats collapse into the agent main session key.
0069: - Groups/channels get their own session keys.
0070: - The session store and transcripts live on the gateway host.
0071: 
0072: Multiple devices/channels can map to the same session, but history is not fully
0073: synced back to every client. Recommendation: use one primary device for long
0074: conversations to avoid divergent context. The Control UI and TUI always show the
0075: gateway-backed session transcript, so they are the source of truth.
0076: 
0077: Details: [Session management](/concepts/session).
0078: 
0079: ## Tool result metadata
0080: 
```
### Session store / transcript / compaction

Source: `openclaw/openclaw-main/docs/reference/session-management-compaction.md` lines 1-90

```
0001: ---
0002: summary: "Deep dive: session store + transcripts, lifecycle, and (auto)compaction internals"
0003: read_when:
0004:   - You need to debug session ids, transcript JSONL, or sessions.json fields
0005:   - You are changing auto-compaction behavior or adding “pre-compaction” housekeeping
0006:   - You want to implement memory flushes or silent system turns
0007: title: "Session management deep dive"
0008: ---
0009: 
0010: OpenClaw manages sessions end-to-end across these areas:
0011: 
0012: - **Session routing** (how inbound messages map to a `sessionKey`)
0013: - **Session store** (`sessions.json`) and what it tracks
0014: - **Transcript persistence** (`*.jsonl`) and its structure
0015: - **Transcript hygiene** (provider-specific fixups before runs)
0016: - **Context limits** (context window vs tracked tokens)
0017: - **Compaction** (manual and auto-compaction) and where to hook pre-compaction work
0018: - **Silent housekeeping** (memory writes that should not produce user-visible output)
0019: 
0020: If you want a higher-level overview first, start with:
0021: 
0022: - [Session management](/concepts/session)
0023: - [Compaction](/concepts/compaction)
0024: - [Memory overview](/concepts/memory)
0025: - [Memory search](/concepts/memory-search)
0026: - [Session pruning](/concepts/session-pruning)
0027: - [Transcript hygiene](/reference/transcript-hygiene)
0028: 
0029: ---
0030: 
0031: ## Source of truth: the Gateway
0032: 
0033: OpenClaw is designed around a single **Gateway process** that owns session state.
0034: 
0035: - UIs (macOS app, web Control UI, TUI) should query the Gateway for session lists and token counts.
0036: - In remote mode, session files are on the remote host; “checking your local Mac files” won’t reflect what the Gateway is using.
0037: 
0038: ---
0039: 
0040: ## Two persistence layers
0041: 
0042: OpenClaw persists sessions in two layers:
0043: 
0044: 1. **Session store (`sessions.json`)**
0045:    - Key/value map: `sessionKey -> SessionEntry`
0046:    - Small, mutable, safe to edit (or delete entries)
0047:    - Tracks session metadata (current session id, last activity, toggles, token counters, etc.)
0048: 
0049: 2. **Transcript (`<sessionId>.jsonl`)**
0050:    - Append-only transcript with tree structure (entries have `id` + `parentId`)
0051:    - Stores the actual conversation + tool calls + compaction summaries
0052:    - Used to rebuild the model context for future turns
0053:    - Large pre-compaction debug checkpoints are skipped once the active
0054:      transcript exceeds the checkpoint size cap, avoiding a second giant
0055:      `.checkpoint.*.jsonl` copy.
0056: 
0057: ---
0058: 
0059: ## On-disk locations
0060: 
0061: Per agent, on the Gateway host:
0062: 
0063: - Store: `~/.openclaw/agents/<agentId>/sessions/sessions.json`
0064: - Transcripts: `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl`
0065:   - Telegram topic sessions: `.../<sessionId>-topic-<threadId>.jsonl`
0066: 
0067: OpenClaw resolves these via `src/config/sessions.ts`.
0068: 
0069: ---
0070: 
0071: ## Store maintenance and disk controls
0072: 
0073: Session persistence has automatic maintenance controls (`session.maintenance`) for `sessions.json`, transcript artifacts, and trajectory sidecars:
0074: 
0075: - `mode`: `warn` (default) or `enforce`
0076: - `pruneAfter`: stale-entry age cutoff (default `30d`)
0077: - `maxEntries`: cap entries in `sessions.json` (default `500`)
0078: - `resetArchiveRetention`: retention for `*.reset.<timestamp>` transcript archives (default: same as `pruneAfter`; `false` disables cleanup)
0079: - `maxDiskBytes`: optional sessions-directory budget
0080: - `highWaterBytes`: optional target after cleanup (default `80%` of `maxDiskBytes`)
0081: 
0082: Normal Gateway writes batch `maxEntries` cleanup for production-sized caps, so a store may briefly exceed the configured cap before the next high-water cleanup rewrites it back down. `openclaw sessions cleanup --enforce` still applies the configured cap immediately.
0083: 
0084: OpenClaw no longer creates automatic `sessions.json.bak.*` rotation backups during Gateway writes. The legacy `session.maintenance.rotateBytes` key is ignored and `openclaw doctor --fix` removes it from older configs.
0085: 
0086: Enforcement order for disk budget cleanup (`mode: "enforce"`):
0087: 
0088: 1. Remove oldest archived, orphan transcript, or orphan trajectory artifacts first.
0089: 2. If still above the target, evict oldest session entries and their transcript/trajectory files.
0090: 3. Keep going until usage is at or below `highWaterBytes`.
```
### Exec approval 设计

Source: `openclaw/openclaw-main/docs/tools/exec-approvals.md` lines 1-80

```
0001: ---
0002: summary: "Host exec approvals: policy knobs, allowlists, and the YOLO/strict workflow"
0003: read_when:
0004:   - Configuring exec approvals or allowlists
0005:   - Implementing exec approval UX in the macOS app
0006:   - Reviewing sandbox-escape prompts and their implications
0007: title: "Exec approvals"
0008: sidebarTitle: "Exec approvals"
0009: ---
0010: 
0011: Exec approvals are the **companion app / node host guardrail** for letting
0012: a sandboxed agent run commands on a real host (`gateway` or `node`). A
0013: safety interlock: commands are allowed only when policy + allowlist +
0014: (optional) user approval all agree. Exec approvals stack **on top of**
0015: tool policy and elevated gating (unless elevated is set to `full`, which
0016: skips approvals).
0017: 
0018: <Note>
0019: Effective policy is the **stricter** of `tools.exec.*` and approvals
0020: defaults; if an approvals field is omitted, the `tools.exec` value is
0021: used. Host exec also uses local approvals state on that machine — a
0022: host-local `ask: "always"` in `~/.openclaw/exec-approvals.json` keeps
0023: prompting even if session or config defaults request `ask: "on-miss"`.
0024: </Note>
0025: 
0026: ## Inspecting the effective policy
0027: 
0028: | Command                                                          | What it shows                                                                          |
0029: | ---------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
0030: | `openclaw approvals get` / `--gateway` / `--node <id\|name\|ip>` | Requested policy, host policy sources, and the effective result.                       |
0031: | `openclaw exec-policy show`                                      | Local-machine merged view.                                                             |
0032: | `openclaw exec-policy set` / `preset`                            | Synchronize the local requested policy with the local host approvals file in one step. |
0033: 
0034: When a local scope requests `host=node`, `exec-policy show` reports that
0035: scope as node-managed at runtime instead of pretending the local
0036: approvals file is the source of truth.
0037: 
0038: If the companion app UI is **not available**, any request that would
0039: normally prompt is resolved by the **ask fallback** (default: `deny`).
0040: 
0041: <Tip>
0042: Native chat approval clients can seed channel-specific affordances on the
0043: pending approval message. For example, Matrix seeds reaction shortcuts
0044: (`✅` allow once, `❌` deny, `♾️` allow always) while still leaving
0045: `/approve ...` commands in the message as a fallback.
0046: </Tip>
0047: 
0048: ## Where it applies
0049: 
0050: Exec approvals are enforced locally on the execution host:
0051: 
0052: - **Gateway host** → `openclaw` process on the gateway machine.
0053: - **Node host** → node runner (macOS companion app or headless node host).
0054: 
0055: ### Trust model
0056: 
0057: - Gateway-authenticated callers are trusted operators for that Gateway.
0058: - Paired nodes extend that trusted operator capability onto the node host.
0059: - Exec approvals reduce accidental execution risk, but are **not** a per-user auth boundary.
0060: - Approved node-host runs bind canonical execution context: canonical cwd, exact argv, env binding when present, and pinned executable path when applicable.
0061: - For shell scripts and direct interpreter/runtime file invocations, OpenClaw also tries to bind one concrete local file operand. If that bound file changes after approval but before execution, the run is denied instead of executing drifted content.
0062: - File binding is intentionally best-effort, **not** a complete semantic model of every interpreter/runtime loader path. If approval mode cannot identify exactly one concrete local file to bind, it refuses to mint an approval-backed run instead of pretending full coverage.
0063: 
0064: ### macOS split
0065: 
0066: - The **node host service** forwards `system.run` to the **macOS app** over local IPC.
0067: - The **macOS app** enforces approvals and executes the command in UI context.
0068: 
0069: ## Settings and storage
0070: 
0071: Approvals live in a local JSON file on the execution host:
0072: 
0073: ```text
0074: ~/.openclaw/exec-approvals.json
0075: ```
0076: 
0077: Example schema:
0078: 
0079: ```json
0080: {
```
### Skills 加载和优先级

Source: `openclaw/openclaw-main/docs/tools/skills.md` lines 1-80

```
0001: ---
0002: summary: "Skills: managed vs workspace, gating rules, agent allowlists, and config wiring"
0003: read_when:
0004:   - Adding or modifying skills
0005:   - Changing skill gating, allowlists, or load rules
0006:   - Understanding skill precedence and snapshot behavior
0007: title: "Skills"
0008: sidebarTitle: "Skills"
0009: ---
0010: 
0011: OpenClaw uses **[AgentSkills](https://agentskills.io)-compatible** skill
0012: folders to teach the agent how to use tools. Each skill is a directory
0013: containing a `SKILL.md` with YAML frontmatter and instructions. OpenClaw
0014: loads bundled skills plus optional local overrides, and filters them at
0015: load time based on environment, config, and binary presence.
0016: 
0017: ## Locations and precedence
0018: 
0019: OpenClaw loads skills from these sources, **highest precedence first**:
0020: 
0021: | #   | Source                | Path                             |
0022: | --- | --------------------- | -------------------------------- |
0023: | 1   | Workspace skills      | `<workspace>/skills`             |
0024: | 2   | Project agent skills  | `<workspace>/.agents/skills`     |
0025: | 3   | Personal agent skills | `~/.agents/skills`               |
0026: | 4   | Managed/local skills  | `~/.openclaw/skills`             |
0027: | 5   | Bundled skills        | shipped with the install         |
0028: | 6   | Extra skill folders   | `skills.load.extraDirs` (config) |
0029: 
0030: If a skill name conflicts, the highest source wins.
0031: 
0032: ## Per-agent vs shared skills
0033: 
0034: In **multi-agent** setups each agent has its own workspace:
0035: 
0036: | Scope                | Path                                        | Visible to                  |
0037: | -------------------- | ------------------------------------------- | --------------------------- |
0038: | Per-agent            | `<workspace>/skills`                        | Only that agent             |
0039: | Project-agent        | `<workspace>/.agents/skills`                | Only that workspace's agent |
0040: | Personal-agent       | `~/.agents/skills`                          | All agents on that machine  |
0041: | Shared managed/local | `~/.openclaw/skills`                        | All agents on that machine  |
0042: | Shared extra dirs    | `skills.load.extraDirs` (lowest precedence) | All agents on that machine  |
0043: 
0044: Same name in multiple places → highest source wins. Workspace beats
0045: project-agent, beats personal-agent, beats managed/local, beats bundled,
0046: beats extra dirs.
0047: 
0048: ## Agent skill allowlists
0049: 
0050: Skill **location** and skill **visibility** are separate controls.
0051: Location/precedence decides which copy of a same-named skill wins; agent
0052: allowlists decide which skills an agent can actually use.
0053: 
0054: ```json5
0055: {
0056:   agents: {
0057:     defaults: {
0058:       skills: ["github", "weather"],
0059:     },
0060:     list: [
0061:       { id: "writer" }, // inherits github, weather
0062:       { id: "docs", skills: ["docs-search"] }, // replaces defaults
0063:       { id: "locked-down", skills: [] }, // no skills
0064:     ],
0065:   },
0066: }
0067: ```
0068: 
0069: <AccordionGroup>
0070:   <Accordion title="Allowlist rules">
0071:     - Omit `agents.defaults.skills` for unrestricted skills by default.
0072:     - Omit `agents.list[].skills` to inherit `agents.defaults.skills`.
0073:     - Set `agents.list[].skills: []` for no skills.
0074:     - A non-empty `agents.list[].skills` list is the **final** set for that
0075:       agent — it does not merge with defaults.
0076:     - The effective allowlist applies across prompt building, skill
0077:       slash-command discovery, sandbox sync, and skill snapshots.
0078:   </Accordion>
0079: </AccordionGroup>
0080: 
```
