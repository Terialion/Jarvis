# Jarvis vs Reference Systems

## Overview

This document compares Jarvis against reference systems in the AI coding assistant space.

## Jarvis Architecture

Jarvis is a modular AI coding assistant built with a pluggable operator architecture, skill harness, and approval-based safety system.

## Reference Systems

- **Cursor**: IDE-integrated AI coding assistant with local file editing
- **Claude Code**: Terminal-based AI agent with tool use capabilities
- **Windsurf/Cline**: Browser-based coding agents

## Capability Comparison

| Capability | Jarvis | Cursor | Claude Code |
|---|---|---|---|
| Local Execution | Yes | Yes | Yes |
| Replay Audit | Yes | No | No |
| Skill Ecosystem | Yes | No | Limited |
| Approval Sandbox | Yes | No | No |

## Design Decisions

Jarvis prioritizes safety, auditability, and extensibility over raw feature parity.
