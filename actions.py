"""Action processing helpers for different platforms."""

from __future__ import annotations

from typing import Any, Callable, Tuple
import json
from time import sleep

from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def parse_bounds(bounds: str) -> Tuple[int, int, int, int]:
    """Parse a bounds string into integer coordinates."""
    left_top, right_bottom = bounds.split("][")
    left, top = map(int, left_top[1:].split(","))
    right, bottom = map(int, right_bottom[:-1].split(","))
    return left, top, right, bottom


def process_web_click(data: dict[str, Any], driver: Any) -> None:
    """Process a click action on web platforms."""
    if "xpath" in data:
        element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, data["xpath"]))
        )
        element.click()
    elif "css" in data:
        element = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, data["css"]))
        )
        element.click()
    elif "bounds" in data:
        left, top, right, bottom = parse_bounds(data["bounds"])
        click_x = left + (right - left) / 2
        click_y = top + (bottom - top) / 2
        driver.execute_script(
            f"document.elementFromPoint({click_x}, {click_y}).click();"
        )


def process_mobile_tap(data: dict[str, Any], driver: Any) -> None:
    """Process a tap action on mobile platforms."""
    if "bounds" in data:
        left, top, right, bottom = parse_bounds(data["bounds"])
        tap_x = left + (right - left) / 2
        tap_y = top + (bottom - top) / 2
        driver.tap([(tap_x, tap_y)])
    elif "xpath" in data:
        element = driver.find_element(AppiumBy.XPATH, data["xpath"])
        element.click()


def process_web_input(data: dict[str, Any], driver: Any) -> None:
    """Process a text input action on web platforms."""
    if "xpath" in data:
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, data["xpath"]))
        )
        element.clear()
        element.send_keys(data["value"])
    elif "css" in data:
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, data["css"]))
        )
        element.clear()
        element.send_keys(data["value"])


def process_mobile_input(data: dict[str, Any], driver: Any) -> None:
    """Process a text input action on mobile platforms."""
    if "bounds" in data:
        left, top, right, bottom = parse_bounds(data["bounds"])
        tap_x = left + (right - left) / 2
        tap_y = top + (bottom - top) / 2
        driver.tap([(tap_x, tap_y)])
        element = driver.find_element(AppiumBy.XPATH, "//*[@focused='true']")
        element.send_keys(data["value"])
        try:
            driver.hide_keyboard()
        except Exception:
            pass
    elif "xpath" in data:
        element = driver.find_element(AppiumBy.XPATH, data["xpath"])
        element.click()
        element = driver.find_element(AppiumBy.XPATH, "//*[@focused='true']")
        element.send_keys(data["value"])
        try:
            driver.hide_keyboard()
        except Exception:
            pass


def process_web_scroll(data: dict[str, Any], driver: Any) -> None:
    """Process a scroll action on web platforms."""
    scroll_x = data.get("swipe_end_x", 0) - data.get("swipe_start_x", 0)
    scroll_y = data.get("swipe_end_y", 0) - data.get("swipe_start_y", 0)
    driver.execute_script(f"window.scrollBy({scroll_x}, {scroll_y});")


def process_mobile_swipe(data: dict[str, Any], driver: Any) -> None:
    """Process a swipe action on mobile platforms."""
    swipe_start_x = data["swipe_start_x"]
    swipe_start_y = data["swipe_start_y"]
    swipe_end_x = data["swipe_end_x"]
    swipe_end_y = data["swipe_end_y"]
    duration = data.get("duration", 500)
    driver.swipe(
        swipe_start_x, swipe_start_y, swipe_end_x, swipe_end_y, duration
    )
    sleep(duration / 1000)


def process_next_action(
    action: str,
    driver: Any,
    folder: str,
    step_name: str,
    platform: str,
    take_page_source_fn: Callable[[Any, str, str, str], str],
    take_screenshot_fn: Callable[[Any, str, str, str], str],
) -> Tuple[str | None, str | None, str]:
    """Process a JSON-formatted action and execute it on the driver."""
    try:
        data = json.loads(action)
    except json.JSONDecodeError:
        print(f"Invalid JSON action: {action}")
        return None, None, '{"action": "error", "result": "Invalid JSON"}'

    if data["action"] in {"error", "finish"}:
        page_source_file = take_page_source_fn(
            driver, folder, step_name, platform
        )
        screenshot_file = take_screenshot_fn(
            driver, folder, step_name, platform
        )
        data["result"] = "success"
        return page_source_file, screenshot_file, json.dumps(data)

    try:
        if data["action"] == "tap":
            if platform == "web":
                process_web_click(data, driver)
            else:
                process_mobile_tap(data, driver)
            data["result"] = "success"
        elif data["action"] == "input":
            if platform == "web":
                process_web_input(data, driver)
            else:
                process_mobile_input(data, driver)
            data["result"] = "success"
        elif data["action"] == "swipe":
            if platform == "web":
                process_web_scroll(data, driver)
            else:
                process_mobile_swipe(data, driver)
            data["result"] = "success"
        elif data["action"] == "wait":
            sleep(data.get("timeout", 5000) / 1000)
            data["result"] = "success"
        else:
            print(f"Unknown action: {data['action']}")
            data["result"] = "unknown action"
    except Exception as err:
        print(f"Error processing action: {err}")
        data["result"] = f"error: {err}"

    page_source_file = take_page_source_fn(driver, folder, step_name, platform)
    screenshot_file = take_screenshot_fn(driver, folder, step_name, platform)
    return page_source_file, screenshot_file, json.dumps(data)
