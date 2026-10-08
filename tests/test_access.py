import pytest

from autoreference import access
from autoreference.config import Settings


class Driver:
    current_url = "https://www.zhizhen.com/s"
    title = "Search"
    page_source = ""
    closed = False

    def find_elements(self, by, selector):
        return [object()]

    def get(self, url):
        self.current_url = url

    def quit(self):
        self.closed = True


def test_access_classification_does_not_guess_403_reason():
    driver = Driver()
    assert access.page_state(driver) == "ready"
    driver.title = "403 forbidden"
    assert access.page_state(driver) == "access_denied"
    driver.title = "Login"
    driver.current_url = "https://school.example/sso/login"
    assert access.page_state(driver) == "requires_login"
    driver.current_url = "chrome-error://chromewebdata"
    assert access.page_state(driver) == "network_required"


def test_login_reuses_dedicated_profile_and_reset_is_scoped(tmp_path, monkeypatch):
    settings = Settings(access_dir=str(tmp_path / "access"))
    driver = Driver()
    monkeypatch.setattr(access, "create_driver", lambda s, headless: driver)
    result = access.login(settings, timeout=1)
    assert result["state"] == "ready"
    assert driver.closed
    profile = access.initialize(settings)
    (profile / "session").write_text("private")
    assert access.initialize(settings) == profile
    assert (profile / "session").exists()
    outside = tmp_path / "keep"
    outside.write_text("unrelated")
    access.reset(settings)
    assert outside.read_text() == "unrelated"
    assert not profile.exists()


def test_reset_refuses_unmanaged_and_linked_directories(tmp_path):
    directory = tmp_path / "unmanaged"
    directory.mkdir()
    (directory / "private").write_text("keep")
    with pytest.raises(ValueError, match="unmanaged"):
        access.reset(Settings(access_dir=str(directory)))
    linked = tmp_path / "linked"
    linked.symlink_to(directory, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic"):
        access.initialize(Settings(access_dir=str(linked)))


def test_cached_access_is_not_current_verification(tmp_path):
    settings = Settings(access_dir=str(tmp_path / "access"))
    assert access.status(settings)["state"] == "not_checked"
    access.save_status(settings, "ready")
    assert "Cached" in access.status(settings)["note"]
