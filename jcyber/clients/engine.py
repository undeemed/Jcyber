"""Cerebras BYOK engine adapter over the OpenAI-compatible endpoint. Output is
evidence-only and never a decision layer (AGENTS.md invariant #7). The key is
read from the operator env var CEREBRAS_API_KEY and never persisted."""

from __future__ import annotations

import os

from openai import OpenAI
from openai.types.chat import ChatCompletionUserMessageParam


class CerebrasEngine:
    def __init__(self, client: OpenAI) -> None:
        self._client = client

    @classmethod
    def from_env(cls, base_url: str = "https://api.cerebras.ai/v1") -> CerebrasEngine:
        return cls(OpenAI(api_key=os.environ["CEREBRAS_API_KEY"], base_url=base_url))

    def augment(self, model: str, prompt: str) -> str:
        message: ChatCompletionUserMessageParam = {"role": "user", "content": prompt}
        resp = self._client.chat.completions.create(model=model, messages=[message])
        return resp.choices[0].message.content or ""
