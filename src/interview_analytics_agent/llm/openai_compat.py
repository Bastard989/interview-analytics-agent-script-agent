from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.llm.errors import ErrCode, ProviderError

log = logging.getLogger(__name__)


@dataclass
class OpenAICompatConfig:
    """Настройки OpenAI-compatible API."""

    api_base: str
    api_key: str
    model: str = "gpt-4o-mini"
    timeout_s: int = 60


class OpenAICompatProvider:
    """Минимальный провайдер LLM через OpenAI-compatible endpoint."""

    def __init__(self) -> None:
        s = get_settings()
        api_base = getattr(s, "openai_api_base", "") or ""
        api_key = getattr(s, "openai_api_key", "") or ""
        model = getattr(s, "openai_model", "gpt-4o-mini") or "gpt-4o-mini"
        timeout_s = int(getattr(s, "openai_timeout_s", 60) or 60)

        if not api_base:
            raise ProviderError(ErrCode.LLM_PROVIDER_ERROR, "OPENAI_API_BASE не задан")
        if not api_key:
            raise ProviderError(ErrCode.LLM_PROVIDER_ERROR, "OPENAI_API_KEY не задан")

        self.cfg = OpenAICompatConfig(
            api_base=api_base, api_key=api_key, model=model, timeout_s=timeout_s
        )

    def complete_text(self, *, system: str, user: str) -> str:
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }

        url = self.cfg.api_base.rstrip("/") + "/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.cfg.timeout_s)
        except requests.RequestException as e:
            log.error(
                "llm_http_error",
                extra={"provider": "openai_compat", "payload": {"err": str(e)}},
            )
            raise ProviderError(
                ErrCode.LLM_PROVIDER_ERROR,
                "Ошибка HTTP при вызове LLM",
                {"err": str(e)},
            ) from e

        if resp.status_code >= 400:
            raise ProviderError(
                ErrCode.LLM_PROVIDER_ERROR,
                "LLM вернул ошибку",
                {"status": resp.status_code, "text_head": resp.text[:500]},
            )

        try:
            data = resp.json()
        except Exception as e:
            raise ProviderError(
                ErrCode.LLM_PROVIDER_ERROR,
                "LLM вернул невалидный JSON",
                {"err": str(e), "text_head": resp.text[:500]},
            ) from e

        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            raise ProviderError(
                ErrCode.LLM_PROVIDER_ERROR,
                "Не удалось извлечь текст из ответа LLM",
                {"err": str(e), "data_head": str(data)[:500]},
            ) from e
