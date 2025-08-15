"""Utilities for creating and maintaining WebDriver instances."""

from __future__ import annotations

from typing import Any
from time import sleep

from appium import webdriver as appium_webdriver
from appium.options.common import AppiumOptions
from selenium import webdriver as selenium_webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions


def create_driver(appium_server: str, platform_config: dict[str, Any]) -> Any:
    """Create a driver based on the provided platform configuration."""
    platform = platform_config.get("platform", "").lower()

    if platform == "ios":
        server = f"http://{appium_server}/wd/hub"
        capabilities = {
            "appium:xcodeSigningId": "App Development",
            "appium:automationName": "XCUITest",
            "platformName": "iOS",
            "appium:deviceName": platform_config.get("deviceName", "iPhone"),
            "appium:udid": platform_config.get("udid"),
            "appium:bundleId": platform_config.get("bundleId"),
            "appium:wdaLocalPort": platform_config.get("wdaLocalPort", "8100"),
            }
        return appium_webdriver.Remote(
            server, options=AppiumOptions().load_capabilities(capabilities)
            )

    if platform == "android":
        server = f"http://{appium_server}/wd/hub"
        capabilities = {
            "platformName": "Android",
            "automationName": "uiautomator2",
            "deviceName": platform_config.get("deviceName", "Android"),
            "appPackage": platform_config.get("appPackage"),
            "appActivity": platform_config.get("appActivity"),
            "language": "en",
            "locale": "US",
        }
        return appium_webdriver.Remote(
            server, options=AppiumOptions().load_capabilities(capabilities)
        )

    if platform == "web":
        browser = platform_config.get("browser", "chrome").lower()
        if browser == "chrome":
            options = ChromeOptions()
            if platform_config.get("headless", False):
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            return selenium_webdriver.Chrome(options=options)
        if browser == "firefox":
            options = FirefoxOptions()
            if platform_config.get("headless", False):
                options.add_argument("--headless")
            return selenium_webdriver.Firefox(options=options)
        raise ValueError(f"Unsupported browser: {browser}")

    raise ValueError(f"Unsupported platform: {platform}")


def keep_driver_live(driver: Any, platform: str) -> None:
    """Keep the driver session alive by periodically accessing it."""
    try:
        while driver:
            if platform == "web":
                driver.current_url
            else:
                driver.page_source
            sleep(10)
    except Exception:
        print("Closing keep-alive thread.")
