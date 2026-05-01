from src.jarvis.core.instructions.schema import InstructionBundle
from src.jarvis.core.llm.provider import FakeLLMProvider, NullLLMProvider
from src.jarvis.core.routing.examples import ROUTING_EXAMPLES
from src.jarvis.core.routing.input_gateway import build_input_envelope
from src.jarvis.core.routing.llm_classifier import classify_intent_with_llm


def test_llm_classifier_parses_json_and_enforces_approval():
    provider = FakeLLMProvider(
        response=(
            '{"intent":"coding_task","response_mode":"coding_loop","confidence":0.88,'
            '"summary":"Create code.","requires_write":false,"requires_approval":false}'
        )
    )
    route = classify_intent_with_llm(
        build_input_envelope("Please add a Python file here."),
        InstructionBundle(combined_text=""),
        ROUTING_EXAMPLES,
        provider,
    )
    assert route is not None
    assert route.intent == "coding_task"
    assert route.requires_write is True
    assert route.requires_approval is True


def test_llm_classifier_returns_none_when_unavailable():
    route = classify_intent_with_llm(
        build_input_envelope("Please add a Python file here."),
        InstructionBundle(combined_text=""),
        ROUTING_EXAMPLES,
        NullLLMProvider(),
    )
    assert route is None
