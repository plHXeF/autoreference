from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

ReasoningEffort = Literal["auto", "none", "low", "medium", "high", "xhigh", "max"]
ApiMode = Literal["responses", "chat_completions"]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration loaded from environment variables only."""

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    query_model: str = "gpt-5.6-luna"
    judge_model: str = "gpt-5.6-terra"
    reasoning_effort: ReasoningEffort = "auto"
    query_max_output_tokens: int = 4_000
    judge_max_output_tokens: int = 12_000
    api_mode: ApiMode = "responses"
    contact_email: str | None = None
    user_agent: str = "AutoReference/0.1"
    request_timeout_seconds: float = 30.0
    zhizhen_url: str = (
        "https://www.zhizhen.com/s?&strchoren=1&size=15&isort=0&x=0_7083&sw={query}"
    )
    chrome_binary: str | None = None
    chromedriver: str | None = None
    browser_headless: bool = True

    @classmethod
    def from_env(cls) -> Settings:
        effort = os.getenv("AUTOREFERENCE_REASONING_EFFORT", "auto").strip().lower()
        valid_efforts = {"auto", "none", "low", "medium", "high", "xhigh", "max"}
        if effort not in valid_efforts:
            raise ValueError(
                "AUTOREFERENCE_REASONING_EFFORT must be one of "
                + ", ".join(sorted(valid_efforts))
            )

        api_mode = os.getenv("AUTOREFERENCE_API_MODE", "responses").strip().lower()
        if api_mode not in {"responses", "chat_completions"}:
            raise ValueError(
                "AUTOREFERENCE_API_MODE must be responses or chat_completions"
            )

        raw_timeout = os.getenv("AUTOREFERENCE_REQUEST_TIMEOUT_SECONDS", "30")
        try:
            timeout = float(raw_timeout)
        except ValueError as exc:
            raise ValueError(
                "AUTOREFERENCE_REQUEST_TIMEOUT_SECONDS must be a number"
            ) from exc

        key = os.getenv("OPENAI_API_KEY") or os.getenv("AUTOREFERENCE_API_KEY")
        return cls(
            openai_api_key=key.strip() if key and key.strip() else None,
            openai_base_url=os.getenv(
                "AUTOREFERENCE_OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            query_model=os.getenv("AUTOREFERENCE_QUERY_MODEL", "gpt-5.6-luna"),
            judge_model=os.getenv("AUTOREFERENCE_JUDGE_MODEL", "gpt-5.6-terra"),
            reasoning_effort=effort,  # type: ignore[arg-type]
            query_max_output_tokens=_env_int(
                "AUTOREFERENCE_QUERY_MAX_OUTPUT_TOKENS", 4_000
            ),
            judge_max_output_tokens=_env_int(
                "AUTOREFERENCE_JUDGE_MAX_OUTPUT_TOKENS", 12_000
            ),
            api_mode=api_mode,  # type: ignore[arg-type]
            contact_email=os.getenv("AUTOREFERENCE_CONTACT_EMAIL") or None,
            user_agent=os.getenv("AUTOREFERENCE_USER_AGENT", "AutoReference/0.1"),
            request_timeout_seconds=timeout,
            zhizhen_url=os.getenv(
                "AUTOREFERENCE_ZHIZHEN_URL",
                cls.__dataclass_fields__["zhizhen_url"].default,
            ),
            chrome_binary=os.getenv("AUTOREFERENCE_CHROME_BINARY") or None,
            chromedriver=os.getenv("AUTOREFERENCE_CHROMEDRIVER") or None,
            browser_headless=_env_bool("AUTOREFERENCE_BROWSER_HEADLESS", True),
        )

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openai_api_key)

    def effort_for(self, task: Literal["query", "judge"]) -> str:
        if self.reasoning_effort != "auto":
            return self.reasoning_effort
        return "low" if task == "query" else "high"

    def public_api_headers(self) -> dict[str, str]:
        user_agent = self.user_agent
        if self.contact_email and "mailto:" not in user_agent:
            user_agent = f"{user_agent} (mailto:{self.contact_email})"
        return {"User-Agent": user_agent, "Accept": "application/json"}

