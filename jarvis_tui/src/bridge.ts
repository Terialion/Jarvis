/**
 * Bridge — communicates with Python backend via stdin/stdout JSON protocol.
 *
 * Architecture:
 *   TUI (parent process, Node/Ink)
 *     └── spawns Python child: python -m jarvis tui_bridge
 *         TUI → Python: stdin (JSON lines)
 *         Python → TUI: stdout (JSON lines)
 *         Python stderr: forwarded to TUI's fd 2 for debugging
 */

import { spawn, type ChildProcess } from "node:child_process";
import { EventEmitter } from "node:events";
import type { PythonEvent, TUIRequest } from "./types.js";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export class JarvisBridge extends EventEmitter {
  private _proc: ChildProcess | null = null;
  private _buffer = "";

  /** Start the Python backend process. */
  start(pythonPath: string, projectRoot: string): void {
    this._proc = spawn(pythonPath, ["-m", "jarvis", "tui_bridge"], {
      cwd: projectRoot,
      stdio: ["pipe", "pipe", "inherit"],
      env: { ...process.env, PYTHONPATH: `${projectRoot}/src`, PYTHONIOENCODING: "utf-8" },
    });

    this._proc.stdout?.on("data", (data: Buffer) => {
      this._buffer += data.toString();
      const lines = this._buffer.split("\n");
      this._buffer = lines.pop() ?? "";

      for (const line of lines) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line) as PythonEvent;
          this.emit("event", event);
          this.emit(event.type, event);
        } catch (err) {
          console.error("[bridge] parse error:", String(err), line.slice(0, 80));
        }
      }
    });

    this._proc.on("close", (code: number | null) => {
      this.emit("closed", code);
    });
  }

  /** Send a request to the Python backend. */
  send(req: TUIRequest): void {
    const stdin = this._proc?.stdin;
    if (!stdin) throw new Error("Bridge not started");
    if (stdin.destroyed) return;
    stdin.write(Buffer.from(JSON.stringify(req) + "\n", "utf-8"));
  }

  /** Stop the Python backend. */
  stop(): void {
    if (this._proc) {
      this.send({ type: "cancel" } as TUIRequest);
      this._proc.kill();
      this._proc = null;
    }
  }

  get running(): boolean {
    return this._proc !== null && !this._proc.killed;
  }
}
