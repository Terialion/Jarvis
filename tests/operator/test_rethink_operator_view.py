import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from jarvis.core.eval.harness_metrics_store import HarnessMetricsStore
from jarvis.core.gateway_state import GatewayReadOnlyAPI, GatewayState


def test_operator_summary_contains_rethink():
    store = HarnessMetricsStore()
    store.append_event({"kind": "rethink", "rethink_trigger": "tool_failed", "risk_tier": "medium"})
    api = GatewayReadOnlyAPI(GatewayState())
    res = api.operator_harness_quality_summary()
    assert res["ok"]
    assert "rethink" in res["data"]
