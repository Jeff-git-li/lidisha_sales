from __future__ import annotations

import os
from typing import Optional

from ai.prompt_builder import build_executive_prompts
from ai.providers.base import AIProvider
from ai.providers.mock import MockProvider
from semantic.ai.executive_context import ExecutiveAIContext, build_executive_ai_context


def get_ai_provider() -> AIProvider:
    provider_name = (os.getenv("AI_PROVIDER") or "mock").strip().lower()
    if provider_name in {"", "mock"}:
        return MockProvider()
    if provider_name == "openai":
        from ai.providers.openai import OpenAIProvider

        return OpenAIProvider()
    raise ValueError(f"Unsupported AI provider: {provider_name}")


def generate_executive_summary(
    provider: Optional[AIProvider] = None,
    context: Optional[ExecutiveAIContext] = None,
) -> str:
    ai_context = context or build_executive_ai_context()
    system_prompt, user_prompt = build_executive_prompts(ai_context)
    ai_provider = provider or get_ai_provider()
    try:
        return ai_provider.generate(system_prompt, user_prompt)
    except Exception as exc:
        return f"AI 今日经营简报暂不可用：{exc}"