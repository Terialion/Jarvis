from __future__ import annotations

from dataclasses import dataclass


class LLMProvider:
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        raise NotImplementedError


@dataclass
class FakeLLMProvider(LLMProvider):
    response: str = "fake llm response"
    prompts: list[dict[str, object]] | None = None

    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        if self.prompts is not None:
            self.prompts.append({"prompt": prompt, "system": system, "temperature": temperature})
        return self.response


class NullLLMProvider(LLMProvider):
    def complete(self, prompt: str, *, system: str | None = None, temperature: float = 0.2) -> str:
        raise RuntimeError("LLM provider unavailable")


def safe_complete(provider: LLMProvider | None, prompt: str, *, system: str | None = None) -> str | None:
    if provider is None:
        return None
    try:
        return provider.complete(prompt, system=system)
    except Exception:
        return None

