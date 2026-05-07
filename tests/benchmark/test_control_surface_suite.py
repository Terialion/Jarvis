from __future__ import annotations

from pathlib import Path

from benchmarks.run_benchmark import run_suite


def test_control_surface_suite_runs_fake():
    result = run_suite("control_surface", model_mode="fake")
    assert result["suite"] == "control_surface"
    assert result["total"] >= 1
    assert result["pass_rate"] == 1.0


def test_web_control_surface_boundary_doc_exists():
    text = Path("docs/web_control_surface.md").read_text(encoding="utf-8")
    assert "Control Surface does not execute tools directly." in text
    assert "If a task requires JavaScript execution, DOM interaction, login flow, button clicking, screenshots, or dynamic-page navigation, it must not be implemented by extending web.fetch. It must be deferred to the future browser/control-surface phase." in text
