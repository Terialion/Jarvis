"""Output Compressor module for Jarvis Core Phase 1."""

from __future__ import annotations

from time import perf_counter

from .result import error_result, ok_result


class OutputCompressor:
    """Compress command/test logs and diffs into short summaries."""

    def __init__(self, max_lines: int = 20, max_chars_per_line: int = 200) -> None:
        self.max_lines = max_lines
        self.max_chars_per_line = max_chars_per_line

    def compress_command_output(self, stdout: str, stderr: str) -> dict:
        started = perf_counter()
        return self._compress_text(
            stdout=stdout or "",
            stderr=stderr or "",
            started=started,
            preferred_markers=["error", "exception", "failed", "traceback"],
            default_summary="command output compressed",
        )

    def compress_test_output(self, stdout: str, stderr: str) -> dict:
        started = perf_counter()
        return self._compress_text(
            stdout=stdout or "",
            stderr=stderr or "",
            started=started,
            preferred_markers=["assertionerror", "failed", "error", "traceback", "collected", "passed"],
            default_summary="test output compressed",
        )

    def compress_diff(self, diff_text: str) -> dict:
        started = perf_counter()
        if diff_text is None:
            return error_result(
                "COMMON_INVALID_INPUT",
                "diff_text must not be None",
                {"diff_text": diff_text},
                started,
            )
        lines = [ln for ln in diff_text.splitlines() if ln.strip()]
        added = sum(1 for ln in lines if ln.startswith("+") and not ln.startswith("+++"))
        removed = sum(1 for ln in lines if ln.startswith("-") and not ln.startswith("---"))
        key_lines = self._trim_lines([ln for ln in lines if ln.startswith(("@@", "+", "-"))], self.max_lines)
        truncated = len(lines) > self.max_lines
        return ok_result(
            {
                "summary": f"diff compressed: +{added}/-{removed}",
                "key_lines": key_lines,
                "truncated": truncated,
            },
            started,
        )

    def _compress_text(
        self,
        stdout: str,
        stderr: str,
        started: float,
        preferred_markers: list[str],
        default_summary: str,
    ) -> dict:
        if not isinstance(stdout, str) or not isinstance(stderr, str):
            return error_result(
                "COMMON_INVALID_INPUT",
                "stdout/stderr must be strings",
                {"stdout_type": str(type(stdout)), "stderr_type": str(type(stderr))},
                started,
            )
        merged_lines = [ln for ln in (stdout + "\n" + stderr).splitlines() if ln.strip()]
        selected: list[str] = []
        lowered_lines = [(ln, ln.lower()) for ln in merged_lines]
        for marker in preferred_markers:
            for original, low in lowered_lines:
                if marker in low and original not in selected:
                    selected.append(original)
                    if len(selected) >= self.max_lines:
                        break
            if len(selected) >= self.max_lines:
                break
        if not selected:
            selected = merged_lines[: self.max_lines]

        key_lines = self._trim_lines(selected, self.max_lines)
        truncated = len(merged_lines) > self.max_lines
        summary = key_lines[0][:120] if key_lines else default_summary
        return ok_result({"summary": summary, "key_lines": key_lines, "truncated": truncated}, started)

    def _trim_lines(self, lines: list[str], max_lines: int) -> list[str]:
        trimmed = []
        for line in lines[:max_lines]:
            if len(line) > self.max_chars_per_line:
                trimmed.append(line[: self.max_chars_per_line] + "...")
            else:
                trimmed.append(line)
        return trimmed

