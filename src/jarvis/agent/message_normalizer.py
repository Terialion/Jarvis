"""Message normalization for model-specific requirements.

Different providers enforce different constraints on message arrays:

- **Qwen**: System messages must be at the beginning. Mid-conversation system
  messages cause ``System message must be at the beginning`` errors.
- **DeepSeek (reasoner)**: System role can be problematic; recommended to
  prepend system content into the first user message.
- **DeepSeek (chat)**: Standard OpenAI-compatible roles. User/assistant
  alternation is stricter but generally tolerant.
- **Generic / OpenAI / OpenRouter**: No special handling needed.

The normalizer is called by RuntimeModelClient right before sending to the
provider, so it acts as a safety net regardless of the code path.
"""

from __future__ import annotations

from typing import Any


def normalize_messages(
    messages: list[dict[str, Any]],
    *,
    provider: str = "",
    model: str = "",
) -> list[dict[str, Any]]:
    """Return a normalized copy of *messages* safe for the given provider."""
    if not messages:
        return messages

    provider_l = provider.lower()
    model_l = model.lower()

    # ── Step 1: Move all system messages to the front, merging into one ──
    messages = _consolidate_system_messages(messages)

    # ── Step 2: Provider-specific rules ──
    if provider_l in ("qwen",):
        messages = _qwen_normalize(messages)

    if provider_l in ("deepseek",):
        messages = _deepseek_normalize(messages, model_l=model_l)

    return messages


def _consolidate_system_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract all system messages, merge into one, place at index 0.

    System messages that appear after user/assistant/tool messages
    are converted to user messages so they stay in position.
    """
    system_contents: list[str] = []
    has_seen_non_system = False
    out: list[dict[str, Any]] = []

    for m in messages:
        role = str(m.get("role") or "")
        content = str(m.get("content") or "")

        if role == "system":
            if not has_seen_non_system:
                # System message before any user/assistant — collect content
                system_contents.append(content)
            else:
                # Mid-conversation system message — convert to user
                out.append({**m, "role": "user"})
        else:
            has_seen_non_system = True
            out.append(m)

    if system_contents:
        out.insert(0, {"role": "system", "content": "\n\n".join(system_contents)})

    return out


def _qwen_normalize(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Qwen requires system messages only at the beginning.

    _consolidate_system_messages already handles this by converting
    mid-conversation system messages to user. Additional rule:
    ensure there are no consecutive user messages (merge them).
    """
    return _merge_consecutive_same_role(messages, roles={"user"})


def _deepseek_normalize(
    messages: list[dict[str, Any]],
    *,
    model_l: str = "",
) -> list[dict[str, Any]]:
    """DeepSeek normalization: user/assistant alternation, reasoner handling."""
    is_reasoner = "reasoner" in model_l

    if is_reasoner:
        # DeepSeek reasoner: system prompt can cause issues.
        # Prepend system content into the first user message.
        messages = _merge_system_into_first_user(messages)

    # Merge consecutive same-role messages
    messages = _merge_consecutive_same_role(messages, roles={"user", "assistant"})

    return messages


def _merge_system_into_first_user(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Prepend system message content to the first user message."""
    if not messages or messages[0].get("role") != "system":
        return messages

    system_content = str(messages[0].get("content") or "")
    del messages[0]

    # Find first user message
    for m in messages:
        if m.get("role") == "user":
            m["content"] = system_content + "\n\n" + str(m.get("content") or "")
            break
    else:
        # No user message found — unlikely, but insert one
        messages.insert(0, {"role": "user", "content": system_content})

    return messages


def _merge_consecutive_same_role(
    messages: list[dict[str, Any]],
    *,
    roles: set[str],
) -> list[dict[str, Any]]:
    """Merge consecutive messages with the same role (for roles in *roles*)."""
    if not messages:
        return messages

    out: list[dict[str, Any]] = [messages[0]]
    for m in messages[1:]:
        role = str(m.get("role") or "")
        content = str(m.get("content") or "")
        prev = out[-1]
        prev_role = str(prev.get("role") or "")

        if role == prev_role and role in roles:
            prev["content"] = str(prev.get("content") or "") + "\n\n" + content
        else:
            out.append(m)

    return out
