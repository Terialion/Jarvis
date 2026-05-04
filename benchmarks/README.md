# Jarvis Benchmark v0.1

This benchmark validates the chat-first agent main loop:

`ChatInput -> AgentLoop.run_turn() -> tool calls/results -> summary -> persistence`

## Commands

```powershell
python benchmarks/run_benchmark.py --suite jarvis_core --max-cases 30
python benchmarks/run_benchmark.py --suite coding --max-cases 20
python benchmarks/run_benchmark.py --suite terminal --max-cases 10
python benchmarks/run_benchmark.py --suite web_research --max-cases 10
python benchmarks/run_benchmark.py --all
```

## Notes

- The runner imports `src.jarvis.agent.loop.AgentLoop`.
- Default execution is offline-friendly via the fake model fallback.
- Reports are written to `benchmarks/reports`.

