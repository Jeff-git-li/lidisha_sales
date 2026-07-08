from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from ai.providers.base import AIProvider


@dataclass(slots=True)
class OpenAIProvider(AIProvider):
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 60.0

    def __post_init__(self) -> None:
        self.model = (self.model or os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
        self.api_key = (self.api_key or os.getenv("OPENAI_API_KEY") or "").strip()
        self.base_url = (self.base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is not set. Set the environment variable before using OpenAIProvider.")

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenAI request failed with HTTP {exc.code}: {error_body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"OpenAI request failed: {exc.reason}") from exc

        choices = response_payload.get("choices") or []
        if not choices:
            raise RuntimeError("OpenAI response did not include any choices.")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if not content.strip():
            raise RuntimeError("OpenAI response did not include summary text.")
        return content.strip()