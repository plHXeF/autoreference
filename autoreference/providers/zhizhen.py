from __future__ import annotations

import asyncio
import urllib.parse

from autoreference.config import Settings
from autoreference.models import ReferenceCandidate
from autoreference.providers.base import ProviderError


class ZhizhenProvider:
    """Optional browser-backed provider; requires local access and remains unverified."""

    name = "zhizhen"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _create_driver(self):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
        except ImportError as exc:
            raise ProviderError(
                "Zhizhen support is not installed. Run: pip install -e .[zhizhen]"
            ) from exc

        options = webdriver.ChromeOptions()
        if self.settings.browser_headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--no-sandbox")
        if self.settings.chrome_binary:
            options.binary_location = self.settings.chrome_binary
        service = Service(self.settings.chromedriver) if self.settings.chromedriver else Service()
        return webdriver.Chrome(service=service, options=options)

    def _search_blocking(self, query: str, limit: int) -> list[ReferenceCandidate]:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.webdriver.support.ui import WebDriverWait

        driver = self._create_driver()
        candidates: list[ReferenceCandidate] = []
        try:
            url = self.settings.zhizhen_url.format(query=urllib.parse.quote(query))
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            wait.until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "h3.fx-column-title > a"))
            )
            links = [
                element.get_attribute("href")
                for element in driver.find_elements(
                    By.CSS_SELECTOR, "h3.fx-column-title > a"
                )[:limit]
            ]
            for detail_url in filter(None, links):
                try:
                    driver.get(detail_url)
                    title = wait.until(
                        EC.presence_of_element_located((By.CLASS_NAME, "title"))
                    ).text.strip()
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
                except Exception:
                    continue
        except Exception as exc:
            raise ProviderError(f"Zhizhen browser search failed: {exc}") from exc
        finally:
            driver.quit()
        return candidates

    async def search(self, query: str, limit: int) -> list[ReferenceCandidate]:
        return await asyncio.to_thread(self._search_blocking, query, limit)

    async def close(self) -> None:
        return None
