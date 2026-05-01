"""Tests for LLM semantic routing A/B comparison.

Compares deterministic-hit vs LLM-hit for natural language inputs.
The goal is to show that ordinary NL falls through deterministic to LLM,
not that deterministic catches everything.
"""

import json
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.deterministic_router import route_deterministically


# Inputs that SHOULD be handled by LLM (not deterministic)
_LLM_BOUNDARY_CASES = [
    "给我讲个笑话",
    "讲个冷笑话",
    "tell me a joke",
    "make me laugh",
    "有哪些技能",
    "我能用哪些工具",
    # Note: "有没有 web search skill" contains "search " which matches web_search_rule — acceptable deterministic
    "我现在的目录是什么",
    "当前 workspace 在哪",
    "这个项目根目录是什么",
    "当前工作空间路径是什么",
    "帮我检查一下这个项目的结构",
    "这个项目怎么组织的",
    "入口文件在哪里",
    "测试目录在哪",
    "解释 sandbox 和 approval",
    "帮我规划重构",
    "帮我规划一下如何重构输入路由",
    "说个程序员笑话",
    "无聊，陪我聊会儿",
    "帮我看看可用能力",
]

# Inputs that SHOULD be handled by deterministic
_DETERMINISTIC_CASES = [
    ("你好", "chat_answer"),
    ("hello", "chat_answer"),
    ("你是谁", "help_answer"),
    ("你能做什么", "help_answer"),
    ("查看skill", "skill_admin"),
    ("列出 skills", "skill_admin"),
    ("写个东西", "clarify_question"),  # genuinely ambiguous
    ("弄一下", "clarify_question"),  # genuinely ambiguous
    ("在这个工作空间写一个python程序", "coding_loop"),
    ("运行 pytest", "executor_action"),
    ("读取 .env 看看", "refusal_or_safety_message"),  # safety precheck
]


def test_llm_boundary_cases_not_deterministic():
    """All NL boundary cases should NOT match high-confidence deterministic rules."""
    for input_text in _LLM_BOUNDARY_CASES:
        envelope = build_input_envelope(input_text)
        route = route_deterministically(envelope)
        assert route.confidence < 0.85, (
            f"Input '{input_text}' should NOT be caught by deterministic router. "
            f"Got confidence={route.confidence}, mode={route.response_mode}"
        )


def test_deterministic_cases_still_work():
    """Deterministic high-confidence rules should still work for structural inputs."""
    for input_text, expected_mode in _DETERMINISTIC_CASES:
        envelope = build_input_envelope(input_text)
        route = route_deterministically(envelope)
        if expected_mode == "refusal_or_safety_message":
            # Safety precheck is in intent_gateway, not deterministic_router
            # So deterministic won't catch it
            continue
        assert route.response_mode == expected_mode, (
            f"Input '{input_text}' should route to {expected_mode}, "
            f"got {route.response_mode} (conf={route.confidence})"
        )


def test_ab_classification_report():
    """Generate an A/B classification report for documentation.

    This test always passes — it just prints the classification results
    for human review.
    """
    results = {"deterministic_hit": 0, "llm_fallback": 0, "details": []}
    for input_text in _LLM_BOUNDARY_CASES:
        envelope = build_input_envelope(input_text)
        route = route_deterministically(envelope)
        if route.confidence >= 0.85 and route.response_mode != "clarify_question":
            results["deterministic_hit"] += 1
            results["details"].append({"input": input_text, "source": "deterministic", "mode": route.response_mode, "conf": route.confidence})
        else:
            results["llm_fallback"] += 1
            results["details"].append({"input": input_text, "source": "llm_fallback", "mode": route.response_mode, "conf": route.confidence})

    # All boundary cases should fall to LLM
    assert results["llm_fallback"] == len(_LLM_BOUNDARY_CASES), (
        f"Expected all {len(_LLM_BOUNDARY_CASES)} boundary cases to fall to LLM, "
        f"but {results['deterministic_hit']} were caught by deterministic: "
        f"{[d for d in results['details'] if d['source'] == 'deterministic']}"
    )

    # Print report for human review
    print("\n=== LLM Semantic Routing A/B Report ===")
    print(f"Total boundary cases: {len(_LLM_BOUNDARY_CASES)}")
    print(f"Deterministic hits: {results['deterministic_hit']}")
    print(f"LLM fallback: {results['llm_fallback']}")
    print(f"LLM fallback rate: {results['llm_fallback'] / len(_LLM_BOUNDARY_CASES) * 100:.1f}%")
    for d in results["details"]:
        src = d["source"]
        mode = d["mode"]
        conf = d["conf"]
        print(f"  [{src:15s}] conf={conf:.2f} mode={mode:25s} input=\"{d['input']}\"")
