"""Token counting with tiktoken (cl100k_base) and fallback heuristic.

All major models use BPE tokenizers close enough to cl100k_base for estimation.
Model context window limits are defined here as the authoritative reference.
"""

from __future__ import annotations

from typing import Any

# Model family → context window size (tokens)
CONTEXT_WINDOWS: dict[str, int] = {
    # OpenAI
    "gpt-4": 128000,
    "gpt-4o": 128000,
    "gpt-4-turbo": 128000,
    "gpt-4.1": 1048576,
    "gpt-4.5": 128000,
    "gpt-3.5": 16385,
    # Anthropic Claude
    "claude-opus-4": 200000,
    "claude-sonnet-4": 200000,
    "claude-haiku-4": 200000,
    "claude-3.5": 200000,
    "claude-3": 200000,
    # DeepSeek
    "deepseek-v3": 128000,
    "deepseek-v4": 128000,
    "deepseek-r1": 128000,
    # Others
    "llama-3": 128000,
    "qwen": 131072,
    "gemini": 1048576,
}
DEFAULT_CONTEXT_WINDOW = 128000


def get_context_window(model_name: str | None) -> int:
    """Return context window size for a model name, with fuzzy matching."""
    if not model_name:
        return DEFAULT_CONTEXT_WINDOW
    name_lower = model_name.lower()
    for prefix, size in CONTEXT_WINDOWS.items():
        if prefix in name_lower:
            return size
    return DEFAULT_CONTEXT_WINDOW


class TokenEstimator:
    """Token counting using tiktoken with chars/3.5 fallback."""

    def __init__(self, model_name: str = "") -> None:
        self._encoding: Any = None
        self._model_name = model_name
        try:
            import tiktoken
            self._encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            pass

    @property
    def has_real_tokenizer(self) -> bool:
        return self._encoding is not None

    def count(self, text: str) -> int:
        """Count tokens in a string."""
        if self._encoding is not None:
            try:
                return len(self._encoding.encode(text))
            except Exception:
                pass
        # Fallback: chars / 3.5 (conservative estimate for code-heavy text)
        return max(1, int(len(text) / 3.5))

    def count_messages(self, messages: list[dict[str, Any]]) -> int:
        """Count tokens across messages including framing overhead.

        Each message has ~4 tokens of framing (role, content markers).
        """
        total = 0
        for msg in messages:
            total += 4  # message framing overhead
            for key, value in msg.items():
                if isinstance(value, str):
                    total += self.count(value)
                elif isinstance(value, (list, dict)):
                    total += self.count(str(value))
        return max(1, total)

    def context_usage_pct(
        self,
        messages: list[dict[str, Any]],
        model_name: str | None = None,
    ) -> float:
        """Return percentage of context window used (0.0–1.0+)."""
        used = self.count_messages(messages)
        window = get_context_window(model_name or self._model_name)
        return used / window if window > 0 else 0.0

    def context_remaining(
        self,
        messages: list[dict[str, Any]],
        model_name: str | None = None,
    ) -> int:
        """Return estimated remaining tokens in context window."""
        used = self.count_messages(messages)
        window = get_context_window(model_name or self._model_name)
        return max(0, window - used)


# Module-level singleton
_estimator: TokenEstimator | None = None


def get_estimator(model_name: str = "") -> TokenEstimator:
    """Return a shared TokenEstimator instance."""
    global _estimator
    if _estimator is None:
        _estimator = TokenEstimator(model_name)
    return _estimator
