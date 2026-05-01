from src.jarvis.core.routing.hybrid_router import route_user_input
from src.jarvis.core.routing.safety_gate import apply_route_safety


def test_sensitive_read_blocked_or_gated():
    routed = route_user_input("读取 .env 看看", source_surface="cli", input_kind="unknown_task")
    safe = apply_route_safety(routed, "读取 .env 看看", mode="safe")
    assert safe.response_mode == "refusal_or_safety_message"
    assert safe.requires_approval is True


def test_destructive_request_blocked_or_gated():
    routed = route_user_input("删除整个项目", source_surface="cli", input_kind="unknown_task")
    safe = apply_route_safety(routed, "删除整个项目", mode="safe")
    assert safe.response_mode == "refusal_or_safety_message"
    assert safe.risk_level == "high"


def test_shell_requires_approval():
    routed = route_user_input("运行 pytest", source_surface="cli", input_kind="test_or_shell_task")
    safe = apply_route_safety(routed, "运行 pytest", mode="safe")
    assert safe.requires_shell is True
    assert safe.requires_approval is True


def test_coding_requires_write_and_approval():
    routed = route_user_input("修复这个 bug，并跑测试", source_surface="cli", input_kind="coding_task")
    safe = apply_route_safety(routed, "修复这个 bug，并跑测试", mode="safe")
    assert safe.requires_write is True
    assert safe.requires_approval is True
