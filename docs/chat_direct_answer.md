# Chat Direct Answer

## Goal

When an LLM provider is available, chat-like inputs should return the provider's final natural-language answer. Local templates are fallback only, and chat path must not emit tool plans or call tools.

## Applies To

- Identity questions, such as "你是谁？你能做什么？"
- Concept explanations, such as "请解释 sandbox 和 approval 的区别。"
- Plan-only requests, especially requests that explicitly say not to edit code
- Jokes, casual chat, and lightweight creative answers
- Vague but answerable questions, such as "下一步该做什么？"

## Does Not Apply To

- Reading files, inspecting the workspace, or opening URLs
- Editing code or creating files
- Running shell commands or tests
- Requests involving API keys, tokens, secrets, or `.env` contents
- Dangerous operations such as deleting project files

Those requests must stay in the work, approval, or safety path.

## Debugging

1. Check the provider status line in `python -m jarvis.cli --ask "..."`
2. For prompt assertions, run `python -m pytest tests/llm/test_chat_direct_answer_prompt.py -q`
3. For dispatcher boundaries, run `python -m pytest tests/cli_response/test_chat_direct_answer_cli_behavior.py -q`
4. For broader SWE-style cases, run `python -m pytest tests/cli_response/test_chat_direct_answer_swe_cases.py -q`

## Pytest Acceptance Commands

```powershell
python -m pytest tests/llm/test_chat_direct_answer_prompt.py -q
python -m pytest tests/cli_response/test_chat_direct_answer_cli_behavior.py -q
python -m pytest tests/cli_response/test_chat_direct_answer_swe_cases.py -q
python -m pytest tests/cli_response/test_chat_llm_priority.py -q
python -m pytest tests/cli_response -q
python -m pytest tests/cli/test_cli_agent_tool_loop_integration.py -q
```

## Real CLI Acceptance Commands

```powershell
python -m jarvis.cli --ask "你是谁？你能做什么？"
python -m jarvis.cli --ask "请解释 sandbox 和 approval 的区别，用简洁的中文说明。"
python -m jarvis.cli --ask "帮我规划一下如何重构输入路由，不要直接改代码。"
python -m jarvis.cli --ask "给我讲一个程序员相关的短笑话。"
python -m jarvis.cli --ask "下一步该做什么？"
python -m jarvis.cli --ask "帮我改一下。"
python -m jarvis.cli --ask "Who are you and what can you do?"
```

## Pass Criteria

- Provider available chat-like inputs return final LLM text.
- No local clarify template appears for identity, explanation, plan-only, joke, or vague-but-answerable inputs.
- Output does not contain `tool_plan` or `tool_calls`.
- Chat path does not call `ToolRuntime`.
- Truly under-specified inputs may ask one minimal clarification question.
- Safety requests remain blocked before LLM chat.
- Work requests remain in the work path and keep approval boundaries.
