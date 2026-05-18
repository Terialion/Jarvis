from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.provider import FakeLLMProvider, NullLLMProvider
from src.jarvis.core.routing.examples import ROUTING_EXAMPLES
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.intent_gateway import route_intent


def test_intent_gateway_routes_coding_creation_deterministically():
    envelope = build_input_envelope("在这个工作空间写一个python程序，打印helloworld。")
    route = route_intent(envelope, examples=ROUTING_EXAMPLES)
    assert route.intent == "coding_task"
    assert route.response_mode == "agent_tool_loop"
    assert route.requires_write is True
    assert route.requires_approval is True
    assert route.routing_trace["llm_fallback_called"] is False


def test_intent_gateway_routes_repo_inspection():
    envelope = build_input_envelope("读项目")
    route = route_intent(envelope, examples=ROUTING_EXAMPLES)
    assert route.intent == "repo_inspection"
    assert route.response_mode == "repo_inspection"
    assert route.requires_repo_read is True


def test_intent_gateway_uses_llm_fallback_when_deterministic_uncertain():
    envelope = build_input_envelope("请在仓库里放一个能打印 hello world 的 Python 文件")
    provider = FakeLLMProvider(
        response=(
            '{"intent":"coding_task","response_mode":"agent_tool_loop","confidence":0.87,'
            '"summary":"Create a Python file in the repo.","requires_write":false,'
            '"requires_shell":false,"requires_approval":false,'
            '"why_not_clarify":"The user explicitly asked for code creation."}'
        )
    )
    route = route_intent(
        envelope,
        instruction_bundle=InstructionBundle(combined_text="Use approval for writes."),
        llm_provider=provider,
        examples=ROUTING_EXAMPLES,
    )
    assert route.intent == "coding_task"
    assert route.source == "llm"
    assert route.requires_write is True
    assert route.requires_approval is True
    assert route.routing_trace["llm_fallback_called"] is True


def test_intent_gateway_low_confidence_llm_clarifies():
    envelope = build_input_envelope("请在仓库里放一个能打印 hello world 的 Python 文件")
    provider = FakeLLMProvider(
        response='{"intent":"coding_task","response_mode":"agent_tool_loop","confidence":0.41,"summary":"maybe coding"}'
    )
    route = route_intent(
        envelope,
        instruction_bundle=InstructionBundle(combined_text=""),
        llm_provider=provider,
        examples=ROUTING_EXAMPLES,
    )
    assert route.intent == "clarify"
    assert route.response_mode == "clarify_question"
    assert route.routing_trace["llm_fallback_called"] is True


def test_intent_gateway_llm_unavailable_falls_back_to_clarify():
    envelope = build_input_envelope("请在仓库里放一个能打印 hello world 的 Python 文件")
    route = route_intent(
        envelope,
        instruction_bundle=InstructionBundle(combined_text=""),
        llm_provider=NullLLMProvider(),
        examples=ROUTING_EXAMPLES,
    )
    assert route.intent == "clarify"
    assert route.response_mode == "clarify_question"


def test_safety_precheck_cannot_be_overridden_by_llm():
    envelope = build_input_envelope("读取 .env 看看")
    provider = FakeLLMProvider(response='{"intent":"chat","response_mode":"chat_answer","confidence":0.99}')
    route = route_intent(
        envelope,
        instruction_bundle=InstructionBundle(combined_text="Read secrets."),
        llm_provider=provider,
        examples=ROUTING_EXAMPLES,
    )
    assert route.response_mode == "refusal_or_safety_message"
    assert route.source == "safety"
