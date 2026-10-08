"""Dedicated local browser sessions for human-operated institutional login."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from autoreference.config import Settings
from autoreference.providers.base import ProviderError


def access_root(settings: Settings) -> Path:
    root = Path(settings.access_dir).expanduser().absolute()
    if root.is_symlink():
        raise ValueError("Access directory must not be a symbolic link.")
    return root


def initialize(settings: Settings) -> Path:
    root = access_root(settings)
    if root.exists() and not (root / ".managed-by-autoreference").is_file():
        raise ValueError("Refusing to use an unmanaged browser directory.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    (root / ".managed-by-autoreference").touch(mode=0o600)
    profile = root / "profile"
    if profile.is_symlink():
        raise ValueError("Browser profile must not be a symbolic link.")
    profile.mkdir(mode=0o700, exist_ok=True)
    return profile


def save_status(settings: Settings, status: str) -> dict:
    initialize(settings)
    value = {
        "source": "zhizhen",
        "state": status,
        "checked_at": time.time(),
        "live_verified": status == "ready",
    }
    file = access_root(settings) / "status.json"
    file.write_text(json.dumps(value), encoding="utf-8")
    os.chmod(file, 0o600)
    return value


def status(settings: Settings) -> dict:
    installed = importlib.util.find_spec("selenium") is not None
    file = access_root(settings) / "status.json"
    value = json.loads(file.read_text()) if file.is_file() else {"state": "not_checked"}
    return {
        "source": "zhizhen",
        **value,
        "browser_dependency_installed": installed,
        "configured_login_url": bool(settings.campus_login_url),
        "note": "Cached state; only a successful live search establishes current access.",
    }


def create_driver(settings: Settings, *, headless: bool):
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
    except ImportError as exc:
        raise ProviderError(
            "Install autoreference[zhizhen] for campus access.", code="browser_unavailable"
        ) from exc
    profile = initialize(settings)
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={profile}")
    if headless:
        options.add_argument("--headless=new")
    if settings.chrome_binary:
        options.binary_location = settings.chrome_binary
    service = Service(settings.chromedriver) if settings.chromedriver else Service()
    try:
        return webdriver.Chrome(service=service, options=options)
    except Exception as exc:
        raise ProviderError(
            "Dedicated browser could not start; check browser/profile availability.",
            code="browser_unavailable",
        ) from exc


def page_state(driver) -> str:
    """Return observable conditions, without guessing why a server rejected access."""
    url = driver.current_url.lower()
    title = driver.title.lower()
    if "403" in title or "forbidden" in title:
        return "access_denied"
    if "chrome-error://" in url or "err_internet_disconnected" in driver.page_source.lower():
        return "network_required"
    if any(word in url for word in ("login", "sso", "authserver")):
        return "requires_login"
    if driver.find_elements("css selector", "h3.fx-column-title > a"):
        return "ready"
    return "parse_error"


def login(settings: Settings, timeout: int = 180) -> dict:
    url = settings.campus_login_url or settings.zhizhen_url.format(query="water")
    if urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Campus login URL must use HTTP or HTTPS.")
    driver = create_driver(settings, headless=False)
    try:
        driver.get(url)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = page_state(driver)
            if state == "ready":
                return save_status(settings, state)
            time.sleep(1)
        return save_status(settings, page_state(driver))
    finally:
        driver.quit()


def reset(settings: Settings) -> dict:
    root = access_root(settings)
    if root.exists():
        if not (root / ".managed-by-autoreference").is_file():
            raise ValueError("Refusing to delete an unmanaged access directory.")
        if (root / "profile").is_symlink():
            raise ValueError("Refusing to delete a linked profile.")
        shutil.rmtree(root)
    return {"source": "zhizhen", "state": "reset"}
