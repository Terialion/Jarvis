/**
 * Entry point — parses CLI arguments and renders the Ink <App>.
 *
 * Usage: tsx src/entry.tsx --python .venv/Scripts/python.exe --cwd D:\agent\Jarvis
 *        [--model deepseek-v4] [--prompt "initial message"]
 */
import React from "react";
import { render } from "ink";
import { readFileSync } from "node:fs";
import { App } from "./app.js";
import { parseArgs } from "node:util";

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    python: { type: "string", default: "python" },
    cwd: { type: "string", default: process.cwd() },
    model: { type: "string", default: "unknown" },
    branch: { type: "string", default: "" },
    mode: { type: "string", default: "default" },
    prompt: { type: "string", default: "" },
  },
});

// Detect git branch from .git/HEAD if not provided
let branch = values.branch;
if (!branch) {
  try {
    const head = readFileSync(`${values.cwd}/.git/HEAD`, "utf-8").trim();
    if (head.startsWith("ref: refs/heads/")) {
      branch = head.slice("ref: refs/heads/".length);
    }
  } catch {
    // Not a git repo or .git not found
  }
}

// Read version from package.json
let version = "0.0.0";
try {
  const pkg = JSON.parse(readFileSync(new URL("../package.json", import.meta.url), "utf-8"));
  version = pkg.version ?? "0.0.0";
} catch {
  // Fallback
}

const { waitUntilExit } = render(
  <App
    pythonPath={values.python}
    projectRoot={values.cwd}
    modelName={values.model}
    gitBranch={branch}
    permissionMode={values.mode}
    initialPrompt={values.prompt}
    version={version}
  />,
);

// Clean up on exit
waitUntilExit().then(() => {
  process.exit(0);
});
