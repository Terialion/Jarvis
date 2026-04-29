from src.jarvis.api.server import JarvisApiState, route_request


def test_create_chat_session():
    state = JarvisApiState()
    status, payload = route_request(
        state,
        "POST",
        "/api/chat",
        {"message": "Help me inspect this project.", "mode": "safe"},
    )
    assert status == 200
    data = payload["data"]
    assert data["session_id"].startswith("chat_")
    assert data["message_id"].startswith("msg_")
    assert "events_url" in data
    assert "websocket_url" in data


def test_get_chat_messages():
    state = JarvisApiState()
    _, created = route_request(state, "POST", "/api/chat", {"message": "hello", "mode": "safe"})
    session_id = created["data"]["session_id"]
    status, payload = route_request(state, "GET", f"/api/chat/{session_id}/messages")
    assert status == 200
    assert len(payload["data"]) >= 1
