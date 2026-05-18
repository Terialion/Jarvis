from src.jarvis.core.routing.examples import ROUTING_EXAMPLES_ZH
from src.jarvis.core.routing.hybrid_router import route_user_input
from src.jarvis.core.routing.safety_gate import apply_route_safety


def test_hybrid_intent_router_zh_examples():
    for sample in ROUTING_EXAMPLES_ZH:
        routed = route_user_input(sample["input"], source_surface="cli", input_kind="unknown_task")
        safe = apply_route_safety(routed, sample["input"])
        assert safe.intent == sample["intent"], sample["input"]
        assert safe.response_mode == sample["mode"], sample["input"]
