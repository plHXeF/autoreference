from __future__ import annotations

import asyncio
import re
import urllib.parse

from autoreference.config import Settings
from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError

MISSING_SELENIUM_MESSAGE = "Zhizhen support is not installed. Run: pip install -e .[zhizhen]"


def _clean_detail_title(value: str) -> str:
    return re.sub(r"^\s*[\[［][^\]］]+[\]］]\s*", "", value).strip()


def _browser_error_detail(exc: Exception, driver) -> str:
    detail = str(exc).strip() or type(exc).__name__
    try:
        return f"{detail} (URL: {driver.current_url}; title: {driver.title})"
    except Exception:
        return detail


class ZhizhenProvider:
    """Optional browser-backed provider; requires local access and remains unverified."""

    name = "zhizhen"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _create_driver(self):
        from autoreference.access import create_driver

        return create_driver(self.settings, headless=self.settings.browser_headless)

    def _search_blocking(self, query: str, limit: int) -> list[ReferenceCandidate]:
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:
            raise ProviderError(MISSING_SELENIUM_MESSAGE, code="browser_unavailable") from exc

        driver = self._create_driver()
        candidates: list[ReferenceCandidate] = []
        detail_errors: list[Exception] = []
        try:
            url = self.settings.zhizhen_url.format(query=urllib.parse.quote(query))
            driver.get(url)
            if "403" in driver.title:
                raise ProviderError(
                    f"Zhizhen access was rejected (URL: {driver.current_url}; "
                    f"title: {driver.title})",
                    code="access_denied",
                )
            wait = WebDriverWait(driver, 15)
            wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "h3.fx-column-title > a"))
            )
            links = [
                element.get_attribute("href")
                for element in driver.find_elements(By.CSS_SELECTOR, "h3.fx-column-title > a")[
                    :limit
                ]
            ]
            for detail_url in filter(None, links):
                try:
                    driver.get(detail_url)
                    title = _clean_detail_title(
                        wait.until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, "div.savelist_con div.card_name > h3.fl")
                            )
                        ).text
                    )
                    try:
                        abstract = driver.find_element(
                            By.XPATH, '//dt[span[text()="摘要"]]/following-sibling::dd[1]'
                        ).text.strip()
                    except Exception:
                        abstract = ""
                    if title:
                        candidates.append(
                            ReferenceCandidate(
                                source=self.name,
                                source_id=detail_url,
                                title=title,
                                abstract=abstract,
                                url=detail_url,
                            )
                        )
                except Exception as exc:
                    detail_errors.append(exc)
                    continue
            if links and not candidates:
                detail = str(detail_errors[0]) if detail_errors else "no detail page was usable"
                raise ProviderError(
                    f"Zhizhen returned {len(links)} detail link(s), "
                    f"but none could be parsed: {detail}"
                )
        except ProviderError as exc:
            from autoreference.access import save_status

            save_status(self.settings, exc.code)
            raise
        except Exception as exc:
            from autoreference.access import page_state, save_status

            state = page_state(driver)
            save_status(self.settings, state)
            raise ProviderError(
                "Zhizhen search could not complete; use public sources or check campus access.",
                code=state,
            ) from exc
        finally:
            driver.quit()
        if candidates:
            from autoreference.access import save_status

            save_status(self.settings, "ready")
        return candidates

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]:
        return await asyncio.to_thread(self._search_blocking, query, limit)

    async def close(self) -> None:
        return None
