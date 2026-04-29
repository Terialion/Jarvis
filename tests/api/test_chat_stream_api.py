from src.jarvis.api.server import JarvisApiState, route_request


def test_chat_events_available():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/chat", {"message": "stream me", "mode": "safe"})
    session_id = created["data"]["session_id"]
    status, payload = route_request(state, "GET", f"/api/chat/{session_id}/events")
    assert status == 200
    event_types = [event["type"] for event in payload["data"]]
    assert "chat.message.created" in event_types
    assert "chat.assistant.completed" in event_types
