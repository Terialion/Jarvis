"""Unified read-only data outlet layer for task/review/gate payloads."""

from __future__ import annotations

from .view_models import (
    build_channels_summary_view,
    build_checkpoint_review_view,
    build_gate_summary_view,
    build_gateway_summary_view,
    build_latest_test_result_view,
    build_nodes_summary_view,
    build_operator_dashboard_view,
    build_review_summary_view,
    build_run_detail_view,
    build_run_list_view,
    build_run_skill_hits_view,
    build_run_step_trace_view,
    build_run_stop_summary_view,
    build_run_tool_calls_view,
    build_release_gate_summary_view,
    build_review_pane_view,
    build_task_summary_view,
    build_task_timeline_view,
)


class DataOutlets:
    """Adapter layer that keeps control-surface output stable."""

    @staticmethod
    def task_summary(task: dict) -> dict:
        return build_task_summary_view(task)

    @staticmethod
    def task_timeline(task: dict, limit: int = 50) -> dict:
        return build_task_timeline_view(task, limit=limit)

    @staticmethod
    def latest_test_result(task: dict) -> dict:
        return build_latest_test_result_view(task)

    @staticmethod
    def checkpoint_review(checkpoint_compare: dict) -> dict:
        return build_checkpoint_review_view(checkpoint_compare)

    @staticmethod
    def review_pane(
        *,
        task: dict,
        rules_warnings: list[dict],
        fallback_policy: dict,
        checkpoint_compare_summary: dict,
        test_result_summary: dict,
        finalize_summary: str | None,
        gate_status: dict,
    ) -> dict:
        return build_review_pane_view(
            task=task,
            rules_warnings=rules_warnings,
            fallback_policy=fallback_policy,
            checkpoint_compare_summary=checkpoint_compare_summary,
            test_result_summary=test_result_summary,
            finalize_summary=finalize_summary,
            gate_status=gate_status,
        )

    @staticmethod
    def gate_summary(gate: dict | None) -> dict:
        return build_release_gate_summary_view(gate)

    @staticmethod
    def operator_run_list(runs: list[dict], limit: int = 20) -> dict:
        return build_run_list_view(runs, limit=limit)

    @staticmethod
    def operator_run_detail(run: dict) -> dict:
        return build_run_detail_view(run)

    @staticmethod
    def operator_run_trace(run: dict, limit: int = 200) -> dict:
        return build_run_step_trace_view(run, limit=limit)

    @staticmethod
    def operator_run_skill_hits(run: dict) -> dict:
        return build_run_skill_hits_view(run)

    @staticmethod
    def operator_run_tool_calls(run: dict) -> dict:
        return build_run_tool_calls_view(run)

    @staticmethod
    def operator_run_stop_summary(run: dict) -> dict:
        return build_run_stop_summary_view(run)

    @staticmethod
    def operator_gateway_summary(runtime_status: dict | None) -> dict:
        return build_gateway_summary_view(runtime_status)

    @staticmethod
    def operator_channels_summary(channels_summary: dict | None) -> dict:
        return build_channels_summary_view(channels_summary)

    @staticmethod
    def operator_nodes_summary(nodes_summary: dict | None) -> dict:
        return build_nodes_summary_view(nodes_summary)

    @staticmethod
    def operator_review_summary(review_summary: dict | None) -> dict:
        return build_review_summary_view(review_summary)

    @staticmethod
    def operator_gate_summary(gate_summary: dict | None) -> dict:
        return build_gate_summary_view(gate_summary)

    @staticmethod
    def operator_dashboard(
        *,
        gateway_summary: dict,
        active_runs_summary: dict,
        recent_runs: dict,
        channels_summary: dict,
        nodes_summary: dict,
        gate_summary: dict,
        review_summary: dict,
        runtime_observability_summary: dict,
    ) -> dict:
        return build_operator_dashboard_view(
            gateway_summary=gateway_summary,
            active_runs_summary=active_runs_summary,
            recent_runs=recent_runs,
            channels_summary=channels_summary,
            nodes_summary=nodes_summary,
            gate_summary=gate_summary,
            review_summary=review_summary,
            runtime_observability_summary=runtime_observability_summary,
        )
