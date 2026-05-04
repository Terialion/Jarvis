# Jarvis LLM Environment Config

## Canonical Variables (Recommended)

Use these four variables as the primary configuration:

```env
JARVIS_LLM_PROVIDER=deepseek
JARVIS_LLM_MODEL=deepseek-chat
JARVIS_LLM_BASE_URL=https://api.deepseek.com
JARVIS_LLM_API_KEY=your_api_key_here
```

Optional tuning:

```env
JARVIS_LLM_TEMPERATURE=0.2
JARVIS_LLM_TIMEOUT_SECONDS=60
JARVIS_LLM_MAX_TOKENS=4096
```

## Resolution Priority

Jarvis resolves LLM env values in this order:

1. Process environment
2. `.env` canonical `JARVIS_LLM_*`
3. Provider-native fallback env names
4. Deprecated legacy aliases (compatibility only, with warning)

## Provider-Native Fallback

Supported fallback env names:

- DeepSeek: `DEEPSEEK_API_KEY`, `DEEPSEEK_API_BASE`
- OpenAI: `OPENAI_API_KEY`, `OPENAI_API_BASE`
- OpenRouter: `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`
- Gemini: `GEMINI_API_KEY` or `GOOGLE_API_KEY`, `GEMINI_BASE_URL`
- MiniMax: `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`
- Ollama: `OLLAMA_API_KEY`, `OLLAMA_BASE_URL`

## Deprecated Aliases

Still compatible, but not recommended:

- `LLM_DEEPSEEK_API_KEY`
- `JARVIS_LLM_DEEPSEEK_API_KEY`
- `LLM_OPENAI_API_KEY`
- `JARVIS_LLM_OPENAI_API_KEY`
- `LLM_OPENAI_API_BASE`
- `JARVIS_LLM_OPENAI_API_BASE`

When deprecated aliases are set, Jarvis emits warnings and includes them in diagnostics as `deprecated_env_used`.

## Base URL Rules

- Set `JARVIS_LLM_BASE_URL` as provider base URL.
- Do **not** set the full endpoint path.
- Jarvis normalizes values and strips:
  - `/v1/chat/completions`
  - `/chat/completions`

## Examples

### DeepSeek

```env
JARVIS_LLM_PROVIDER=deepseek
JARVIS_LLM_MODEL=deepseek-chat
JARVIS_LLM_BASE_URL=https://api.deepseek.com
JARVIS_LLM_API_KEY=sk-xxxx
```

### OpenAI

```env
JARVIS_LLM_PROVIDER=openai
JARVIS_LLM_MODEL=gpt-4.1-mini
JARVIS_LLM_BASE_URL=https://api.openai.com
JARVIS_LLM_API_KEY=sk-xxxx
```

### OpenRouter

```env
JARVIS_LLM_PROVIDER=openrouter
JARVIS_LLM_MODEL=openai/gpt-4.1-mini
JARVIS_LLM_BASE_URL=https://openrouter.ai/api
JARVIS_LLM_API_KEY=sk-or-xxxx
```

### Custom OpenAI-Compatible Server

```env
JARVIS_LLM_PROVIDER=custom
JARVIS_LLM_MODEL=your-model
JARVIS_LLM_BASE_URL=http://127.0.0.1:8000
JARVIS_LLM_API_KEY=optional_or_server_specific
```

## API Connectivity Check

Run:

```powershell
python scripts/check_llm_api.py
```

Success marker:

```text
RESULT: LLM_API_OK
```
