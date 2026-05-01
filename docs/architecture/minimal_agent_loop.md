# Minimal Agent Loop

## Overview

The minimal agent loop is the core execution cycle in Jarvis. It processes user input through a series of well-defined steps to produce a final response.

## User input

The loop begins with raw user input, which is parsed and contextualized.

## Intent / Policy

The intent is extracted and checked against configured policies to determine the appropriate action path.

## Tool call

Based on the resolved intent, one or more tool calls are dispatched to the execution layer.

## Approval

High-risk tool calls require explicit approval before execution. The approval gate enforces safety policies.

## Replay

Completed operations can be replayed for verification or auditing purposes. Replay events are stored as artifacts, e.g. `minimal_loop_trace.json`.

## Memory

The loop writes relevant context back to the memory system for future retrieval and learning.

## Final response

After all steps complete, the loop synthesizes the results into a coherent final response.

## Demo / Quickstart

To see the minimal agent loop in action, run the demo script: `scripts/run_minimal_agent_loop_demo.py`

## Architecture Diagram

The loop flows through the pipeline stages sequentially, with recovery paths at each stage.
