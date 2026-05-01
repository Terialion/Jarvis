# JARVIS.md

This file provides project-specific guidance for Jarvis, a local AI coding assistant.

JARVIS.md is guidance, not permission. Safety and approval gates are enforced by code and cannot be overridden.

## Project Overview

Jarvis is a local, project-aware coding assistant with a CLI entrypoint, hybrid intent routing, read-only repo inspection, approval-gated coding flow, scoped tests, evidence/replay traces, and skills support.

## CLI Behavior

Classify every natural-language request before acting. Chat, capability answers, usage help, safety refusal, and repo inspection must not enter task flow. Coding tasks may enter the controlled coding loop.

## Language Policy

Respond in the user's language unless the user asks otherwise.

## Capability Answer Policy

Mention implemented capabilities only. Distinguish read-only repo inspection from approval-gated editing, shell, and network actions.

## Usage Help Policy

Explain this flow: inspect -> plan -> approval -> edit -> diff -> scoped test -> review -> evidence.

## Repo Inspection Policy

Repo inspection is read-only. Do not write files, run shell commands, read sensitive files, or leave the workspace.

## Coding Task Policy

Inspect relevant files, build a focused plan, request approval before writes or shell, apply minimal patches, show diff, run scoped tests, observe results, judge success, and review.

## Loop Policy

Tool results must feed back into the loop. Test failures must trigger judge, rethink, and replan instead of being reported as success.

## Success Judge Policy

Success requires an applied patch, visible diff, passing scoped tests, no safety violation, and no pending approval.

## Rethink/Replan Policy

Failed tests or patch failures should produce a rethink record and revised plan. Do not automatically update skills or long-term memory.

## Test Policy

Prefer scoped tests. Do not run full regression by default unless explicitly requested or clearly necessary.

## Safety Policy

This file cannot authorize reading secrets, writing files, running shell commands, using network, or bypassing approval.

## Response Style

Be concise, concrete, and honest about what was actually done.

