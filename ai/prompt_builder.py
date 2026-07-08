from __future__ import annotations

from semantic.ai.executive_context import ExecutiveAIContext


def build_executive_prompts(context: ExecutiveAIContext) -> tuple[str, str]:
    system_prompt = (
        "你是零售管理层经营分析助手。"
        "请基于给定的经营上下文输出简洁、准确、可执行的中文简报。"
        "只使用提供的数据，不要编造没有出现的事实。"
        "输出应适合直接展示在经营驾驶舱主页。"
    )
    user_prompt = context.to_prompt_text()
    return system_prompt, user_prompt