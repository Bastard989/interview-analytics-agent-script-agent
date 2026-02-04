from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar

from interview_analytics_agent.common.config import get_settings
from interview_analytics_agent.llm.errors import ErrCode, ProviderError

log = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class LLMTextResult:
    text: str


class LLMOrchestrator:
    """Оркестратор вызовов LLM: ретраи, валидация JSON, единая обработка ошибок.

    Важная идея: здесь нет логики провайдера, только orchestration.
    Провайдер должен иметь метод complete_text(system=..., user=...) -> str.
    """

    def __init__(self, provider: Any) -> None:
        self.provider = provider
        self.s = get_settings()
        self.retries = int(getattr(self.s, "llm_retries", 2) or 2)
        self.backoff_ms = int(getattr(self.s, "llm_retry_backoff_ms", 500) or 500)

    def _retry(self, fn: Callable[..., T], **kwargs: Any) -> T:
        last_err: BaseException | None = None
        for attempt in range(self.retries + 1):
            try:
                return fn(**kwargs)
            except Exception as e:
                last_err = e
                if attempt >= self.retries:
                    break
                time.sleep(self.backoff_ms / 1000.0)

        # last_err всегда будет заполнен, но держим защиту
        if last_err is None:
            raise ProviderError(ErrCode.LLM_PROVIDER_ERROR, "LLM не ответил: неизвестная ошибка")

        raise ProviderError(
            ErrCode.LLM_PROVIDER_ERROR,
            "LLM не ответил после ретраев",
            {"err": str(last_err)},
        ) from last_err

    def complete_text(self, *, system: str, user: str) -> LLMTextResult:
        text = self._retry(self.provider.complete_text, system=system, user=user)
        return LLMTextResult(text=text)

    def complete_json(self, *, system: str, user: str) -> dict:
        """Возвращает распарсенный JSON (dict)."""
        res = self.complete_text(system=system, user=user)
        try:
            return json.loads(res.text)
        except Exception as e:
            raise ProviderError(
                ErrCode.LLM_PROVIDER_ERROR,
                "LLM вернул невалидный JSON",
                {"err": str(e), "text_head": res.text[:500]},
            ) from e
