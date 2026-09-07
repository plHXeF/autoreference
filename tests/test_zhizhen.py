import builtins

import pytest

from autoreference.config import Settings
from autoreference.providers.base import ProviderError
from autoreference.providers.zhizhen import (
    ZhizhenProvider,
    _browser_error_detail,
    _clean_detail_title,
)


class FakeDriver:
    current_url = "https://login.zhizhen.com/findlogin.jsp"
    title = "出错了(403)"


def test_clean_detail_title_removes_publication_type() -> None:
    assert _clean_detail_title("[期刊] Water quality assessment") == "Water quality assessment"
    assert _clean_detail_title("［学位论文］ 地下水评价") == "地下水评价"
    assert _clean_detail_title("Title without a type") == "Title without a type"


def test_browser_error_includes_page_context() -> None:
    detail = _browser_error_detail(TimeoutError(), FakeDriver())

    assert "TimeoutError" in detail
    assert "login.zhizhen.com" in detail
    assert "403" in detail


def test_missing_selenium_has_an_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def without_selenium(name: str, *args, **kwargs):
        if name == "selenium" or name.startswith("selenium."):
            raise ImportError("Selenium is unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_selenium)

    with pytest.raises(ProviderError, match=r"pip install -e .*\[zhizhen\]"):
        ZhizhenProvider(Settings())._search_blocking("water", 1)
