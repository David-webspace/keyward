"""模型轉接：只做一件事，強制模型呼叫一個工具，回傳符合 schema 的結構化結果。

- anthropic：Claude 官方 API（tool_choice 指定工具；不支援強制指定的模型改用 auto 並在提示中要求）
- openai_compatible：Ollama、vLLM、Azure OpenAI 等（tool_choice 指定函式；伺服器沒回工具呼叫時從文字抓 JSON）
"""

import json
import re
import time
from dataclasses import dataclass
from typing import Protocol

from app.config import Settings


@dataclass
class Extraction:
    args: dict | None
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float
    raw: str = ""


class LLM(Protocol):
    def extract(self, system: str, user: str, tool_name: str, tool_description: str, schema: dict) -> Extraction: ...


class AnthropicLLM:
    def __init__(self, s: Settings) -> None:
        import anthropic

        self._sdk, self.model = anthropic, s.llm_model
        self.client = anthropic.Anthropic(api_key=s.llm_api_key, base_url=s.llm_base_url or None)
        self.forced = True

    def extract(self, system, user, tool_name, tool_description, schema) -> Extraction:
        start = time.monotonic()
        kwargs = dict(model=self.model, max_tokens=2048, messages=[{"role": "user", "content": user}],
                      tools=[{"name": tool_name, "description": tool_description, "input_schema": schema}])
        r = None
        if self.forced:
            try:
                r = self.client.messages.create(system=system, tool_choice={"type": "tool", "name": tool_name}, **kwargs)
            except self._sdk.BadRequestError as e:
                if "tool_choice" not in str(e):
                    raise
                self.forced = False
        if r is None:
            r = self.client.messages.create(system=f"{system}\n\n請一定要呼叫 {tool_name} 工具回傳結果。",
                                            tool_choice={"type": "auto"}, **kwargs)
        call = next((b for b in r.content if b.type == "tool_use"), None)
        return Extraction(dict(call.input) if call else None, r.model, r.usage.input_tokens, r.usage.output_tokens,
                          time.monotonic() - start)


_JSON = re.compile(r"\{.*\}", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S)


class OpenAICompatibleLLM:
    def __init__(self, s: Settings) -> None:
        import openai

        self.model, self.effort = s.llm_model, s.llm_reasoning_effort
        self.client = openai.OpenAI(api_key=s.llm_api_key or "not-needed", base_url=s.llm_base_url, timeout=180)

    def extract(self, system, user, tool_name, tool_description, schema) -> Extraction:
        start = time.monotonic()
        kwargs = dict(model=self.model, max_tokens=4096,
                      messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                      tools=[{"type": "function", "function": {"name": tool_name, "description": tool_description,
                                                               "parameters": schema}}],
                      tool_choice={"type": "function", "function": {"name": tool_name}})
        if self.effort:
            kwargs["reasoning_effort"] = self.effort
        r = self.client.chat.completions.create(**kwargs)
        m = r.choices[0].message
        raw = m.tool_calls[0].function.arguments if m.tool_calls else _THINK.sub("", m.content or "")
        try:
            args = json.loads(raw) if m.tool_calls else json.loads(_JSON.search(raw).group(0))
        except (json.JSONDecodeError, AttributeError):
            args = None
        u = r.usage
        return Extraction(args, r.model or self.model, u.prompt_tokens if u else 0, u.completion_tokens if u else 0,
                          time.monotonic() - start, raw)


PROVIDERS = {"anthropic": AnthropicLLM, "openai_compatible": OpenAICompatibleLLM}


def not_configured(s: Settings) -> str | None:
    if not s.llm_provider:
        return "尚未設定模型（LLM_PROVIDER），AI 規則提案功能停用中"
    if s.llm_provider not in PROVIDERS:
        return f"不支援的 LLM_PROVIDER「{s.llm_provider}」"
    if not s.llm_model:
        return "尚未設定 LLM_MODEL"
    if s.llm_provider == "anthropic" and not s.llm_api_key:
        return "尚未設定 LLM_API_KEY"
    if s.llm_provider == "openai_compatible" and not s.llm_base_url:
        return "openai_compatible 需要設定 LLM_BASE_URL"
    return None


def make_llm(s: Settings) -> LLM:
    return PROVIDERS[s.llm_provider](s)
