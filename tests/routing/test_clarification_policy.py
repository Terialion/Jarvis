"""Tests for ClarificationPolicy — DEPRECATED.

These tests verify the deprecated ClarificationPolicy behavior in clarification.py.
They test behavior that is NO LONGER on the default runtime path.
Default path uses: AgentLoop._build_clarification_if_needed() instead.

These tests will emit DeprecationWarning because clarification.py is deprecated.
They are kept for regression coverage of the legacy JARVIS_CLI_LEGACY_NL=1 path.
"""

import warnings

import pytest

from src.jarvis.core.routing.clarification import build_clarification_route
from src.jarvis.core.routing.input_gateway import build_input_envelope


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_clarification_policy_asks_specific_non_code_question():
    route = build_clarification_route(build_input_envelope("写一段说明"), reason="needs_specificity")
    assert "普通说明文本" in (route.clarify_question or "")
    assert "代码文件" in (route.clarify_question or "")


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
def test_clarification_policy_handles_generic_ambiguous_input():
    route = build_clarification_route(build_input_envelope("弄一下"), reason="generic_ambiguous")
    assert "读项目" in (route.clarify_question or "")
    assert "修改代码" in (route.clarify_question or "")
