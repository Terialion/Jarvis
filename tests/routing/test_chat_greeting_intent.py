from src.jarvis.core.routing.hybrid_router import route_user_input


def test_chinese_greeting_routes_to_chat_answer():
    route = route_user_input("你好啊", source_surface="cli", input_kind="unknown_task")
    assert route.intent == "chat"
    assert route.response_mode == "chat_answer"
    assert route.should_clarify is False


def test_english_greeting_routes_to_chat_answer():
    route = route_user_input("hello", source_surface="cli", input_kind="unknown_task")
    assert route.intent == "chat"
    assert route.response_mode == "chat_answer"
    assert route.should_clarify is False
