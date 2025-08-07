"""Universal AI Testing Tool.

Provides cross-platform driver and action management for automated
testing.
"""

import argparse
import datetime
import json
import os
import threading
import base64
import requests
from time import sleep
from appium import webdriver as appium_webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium import webdriver as selenium_webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from PIL import Image, ImageDraw, ImageFont
import xml.etree.ElementTree as ET
import yaml
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)


class PlatformDetector:
    @staticmethod
    def detect_platform(page_source):
        """Detect platform based on page source structure"""
        if (
            "<html" in page_source.lower()
            or "<!doctype html" in page_source.lower()
        ):
            return "web"
        elif "XCUIElementType" in page_source:
            return "ios"
        elif (
            "android" in page_source.lower()
            or "hierarchy" in page_source.lower()
        ):
            return "android"
        else:
            return "unknown"


def read_file_content(file_path):
    try:
        with open(file_path, "r") as file:
            content = file.read()
        return content
    except FileNotFoundError:
        logging.error("The file '%s' does not exist.", file_path)
    except IOError:
        logging.error("Unable to read the file '%s'.", file_path)


def create_folder(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


def image_to_base64(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def generate_next_action(
    prompt, task, history_actions, page_source_file, page_screenshot, platform
):
    screenshot_base64 = image_to_base64(page_screenshot)
    page_source = read_file_content(page_source_file)
    history_actions_str = "\n".join(history_actions)

    # Platform-specific context
    platform_context = {
        "ios": "iOS XML with XCUIElementType elements",
        "android": "Android XML with android hierarchy",
        "web": "HTML DOM structure",
    }

    # Prepare the prompt for Ollama with platform context
    full_prompt = f"""{prompt}

# Platform: {platform.upper()}
Current platform detected: {platform_context.get(platform, 'Unknown platform')}

# Current Task
{task}

# History of Actions
{history_actions_str}

# Current Page Source ({platform.upper()})
```{'xml' if platform in ['ios', 'android'] else 'html'}
{page_source}
```

Based on the current {platform.upper()} screenshot and source above, determine the next action to complete the task.

IMPORTANT FOR {platform.upper()}:
{get_platform_specific_instructions(platform)}

Next action:"""

    # Ollama API payload
    payload = {
        "model": "llama3:70b",
        "prompt": full_prompt,
        "images": [screenshot_base64],
        "stream": False,
        "options": {"num_predict": 200},
    }

    try:
        response = requests.post(
            "http://172.30.91.194:11434/api/generate",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=300,
        )
        response.raise_for_status()

        result = response.json()
        content = result.get("response", "")
        logging.info("LLM response: %s", content)
        return content

    except requests.exceptions.RequestException as e:
        logging.error("Error calling Ollama API: %s", e)
        return '{"action": "error", "reason": "API call failed"}'
    except json.JSONDecodeError as e:
        logging.error("Error parsing Ollama response: %s", e)
        return '{"action": "error", "reason": "Invalid JSON response"}'


def get_platform_specific_instructions(platform):
    """Return platform-specific instructions for the AI model"""
    if platform == "ios":
        return """- Use iOS element types: XCUIElementTypeButton, XCUIElementTypeTextField, etc.
- Use @name, @label, @value attributes for identification
- Calculate bounds from x, y, width, height attributes: [x,y][x+width,y+height]
- Example XPath: //XCUIElementTypeButton[@name='Info'][@enabled='true']"""

    elif platform == "android":
        return """- Use Android element types and attributes
- Use @text, @resource-id, @content-desc for identification
- Use bounds attribute directly: bounds="[x1,y1][x2,y2]"
- Example XPath: //*[@text='Settings'] or //*[@resource-id='com.app:id/button']"""

    elif platform == "web":
        return """- Use standard HTML elements: button, input, div, span, etc.
- Use id, class, name, text content for identification
- Use CSS selectors or XPath for web elements
- Example XPath: //button[text()='Submit'] or //input[@id='username']
- For bounds, use element.location and element.size from Selenium"""

    return "- Platform not recognized, use generic selectors"


def create_driver(appium_server, platform_config):
    """Create appropriate driver based on platform configuration"""
    platform = platform_config.get("platform", "").lower()
    logging.info("Creating driver for platform: %s", platform)

    if platform == "ios":
        appium_server = f"http://{appium_server}/wd/hub"
        capabilities = {
            "appium:xcodeSigningId": "App Development",
            "appium:automationName": "XCUITest",
            "platformName": "iOS",
            "appium:deviceName": platform_config.get("deviceName", "iPhone"),
            "appium:udid": platform_config.get("udid"),
            "appium:bundleId": platform_config.get("bundleId"),
            "appium:wdaLocalPort": platform_config.get("wdaLocalPort", "8100"),
        }
        driver = appium_webdriver.Remote(
            appium_server,
            options=AppiumOptions().load_capabilities(capabilities),
        )
        logging.info("iOS driver initialized")
        return driver

    elif platform == "android":
        appium_server = f"http://{appium_server}/wd/hub"
        capabilities = {
            "platformName": "Android",
            "automationName": "uiautomator2",
            "deviceName": platform_config.get("deviceName", "Android"),
            "appPackage": platform_config.get("appPackage"),
            "appActivity": platform_config.get("appActivity"),
            "language": "en",
            "locale": "US",
        }
        driver = appium_webdriver.Remote(
            appium_server,
            options=AppiumOptions().load_capabilities(capabilities),
        )
        logging.info("Android driver initialized")
        return driver

    elif platform == "web":
        browser = platform_config.get("browser", "chrome").lower()
        if browser == "chrome":
            options = ChromeOptions()
            if platform_config.get("headless", False):
                options.add_argument("--headless")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            driver = selenium_webdriver.Chrome(options=options)
            logging.info("Chrome driver initialized")
            return driver
        elif browser == "firefox":
            options = FirefoxOptions()
            if platform_config.get("headless", False):
                options.add_argument("--headless")
            driver = selenium_webdriver.Firefox(options=options)
            logging.info("Firefox driver initialized")
            return driver
        else:
            logging.error("Unsupported browser: %s", browser)
            raise ValueError(f"Unsupported browser: {browser}")

    else:
        logging.error("Unsupported platform: %s", platform)
        raise ValueError(f"Unsupported platform: {platform}")


def resize_image(img, max_long=2048, max_short=768):
    """Resize the image maintaining aspect ratio"""
    original_width, original_height = img.size
    aspect_ratio = original_width / original_height

    if aspect_ratio > 1:
        new_width = min(original_width, max_long)
        new_height = int(new_width / aspect_ratio)
        new_height = min(new_height, max_short)
        new_width = int(new_height * aspect_ratio)
    else:
        new_height = min(original_height, max_long)
        new_width = int(new_height * aspect_ratio)
        new_width = min(new_width, max_short)
        new_height = int(new_width / aspect_ratio)

    return img.resize((new_width, new_height))


def format_image(image_path, output_path):
    """Format image for consistent processing"""
    with Image.open(image_path) as img:
        width, height = img.size
        new_img = Image.new("RGB", (width, height), "white")
        new_img.paste(img)
        resize_image(new_img).save(output_path)


def write_to_file(file_path, string_to_write):
    with open(file_path, "w") as file:
        file.write(string_to_write)
    return file_path


def remove_unexpected_attr(node):
    """Remove unexpected attributes for mobile XML"""
    unexpected_keys = [
        key
        for key, value in node.attrib.items()
        if key
        not in [
            "index",
            "package",
            "class",
            "text",
            "resource-id",
            "content-desc",
            "clickable",
            "scrollable",
            "bounds",
            "name",
            "label",
            "value",
            "enabled",
            "visible",
            "accessible",
            "x",
            "y",
            "width",
            "height",
        ]
    ]
    for key in unexpected_keys:
        del node.attrib[key]
    for child in node:
        remove_unexpected_attr(child)


def xml_to_dict(xml_element: ET.Element):
    """Convert XML element to dictionary"""
    result = {}
    for child in xml_element:
        child_dict = xml_to_dict(child)
        if child_dict:
            if child.tag in result and result[child.tag]:
                result[child.tag].append(child_dict)
            else:
                result[child.tag] = [child_dict]

    if xml_element.text and xml_element.text.strip():
        text = xml_element.text.strip()
        if "content" in result and result["content"]:
            result["content"].append(text)
        else:
            result["content"] = [text]

    # Include all relevant attributes
    expected_attrib = {
        (key, value)
        for key, value in xml_element.attrib.items()
        if key
        in [
            "index",
            "package",
            "class",
            "text",
            "resource-id",
            "content-desc",
            "clickable",
            "scrollable",
            "bounds",
            "name",
            "label",
            "value",
            "enabled",
            "visible",
            "accessible",
            "x",
            "y",
            "width",
            "height",
        ]
        and value.strip()
    }
    if expected_attrib:
        result.update(expected_attrib)
    return result


def xml_str_to_yaml(yaml_file, xml_str):
    """Convert XML string to YAML file"""
    try:
        root = ET.fromstring(xml_str)
        xml_dict = xml_to_dict(root)
        yaml_data = yaml.dump(xml_dict, default_flow_style=False)
        return write_to_file(yaml_file, yaml_data)
    except ET.ParseError:
        # If it's not valid XML (like HTML), save as text
        return write_to_file(yaml_file, xml_str)


def take_page_source(driver, folder, name, platform):
    """Take page source based on platform"""
    if platform == "web":
        page_source = driver.page_source
        write_to_file(f"{folder}/{name}.html", page_source)
        write_to_file(
            f"{folder}/{name}.yaml", page_source
        )  # For web, just save HTML as text
        logging.info("Saved page source to %s/%s.yaml", folder, name)
        return f"{folder}/{name}.yaml"
    else:
        # Mobile platforms
        write_to_file(f"{folder}/{name}.xml", driver.page_source)
        logging.info("Saved page source to %s/%s.yaml", folder, name)
        return xml_str_to_yaml(f"{folder}/{name}.yaml", driver.page_source)


def take_screenshot(driver, folder, name, platform):
    """Take screenshot based on platform"""
    screenshot_path = f"{folder}/{name}.png"

    if platform == "web":
        driver.save_screenshot(screenshot_path)
    else:
        # Mobile platforms
        driver.save_screenshot(screenshot_path)

    format_image(screenshot_path, f"{folder}/{name}.jpg")
    logging.info("Saved screenshot to %s/%s.jpg", folder, name)
    return f"{folder}/{name}.jpg"


def parse_bounds(bounds):
    """Parse bounds string to coordinates"""
    left_top, right_bottom = bounds.split("][")
    left, top = map(int, left_top[1:].split(","))
    right, bottom = map(int, right_bottom[:-1].split(","))
    return (left, top, right, bottom)


def process_next_action(action, driver, folder, step_name, platform):
    """Process next action based on platform"""
    try:
        data = json.loads(action)
    except json.JSONDecodeError:
        logging.error("Invalid JSON action: %s", action)
        return (None, None, '{"action": "error", "result": "Invalid JSON"}')

    if data["action"] == "error" or data["action"] == "finish":
        page_source_file = take_page_source(driver, folder, step_name, platform)
        screenshot_file = take_screenshot(driver, folder, step_name, platform)
        data["result"] = "success"
        return (page_source_file, screenshot_file, json.dumps(data))

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
            logging.warning("Unknown action: %s", data["action"])
            data["result"] = "unknown action"

    except Exception as e:
        logging.exception("Error processing action")
        data["result"] = f"error: {str(e)}"

    page_source_file = take_page_source(driver, folder, step_name, platform)
    screenshot_file = take_screenshot(driver, folder, step_name, platform)
    return (page_source_file, screenshot_file, json.dumps(data))


def process_web_click(data, driver):
    """Process web click action"""
    logging.info("Web click: %s", data)
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
        # For web, we'll need to convert bounds to element coordinates
        # This is a simplified approach
        left, top, right, bottom = parse_bounds(data["bounds"])
        click_x = left + (right - left) / 2
        click_y = top + (bottom - top) / 2
        driver.execute_script(
            f"document.elementFromPoint({click_x}, {click_y}).click();"
        )


def process_mobile_tap(data, driver):
    """Process mobile tap action"""
    logging.info("Mobile tap: %s", data)
    if "bounds" in data:
        bounds = data["bounds"]
        left, top, right, bottom = parse_bounds(bounds)
        tap_x = left + (right - left) / 2
        tap_y = top + (bottom - top) / 2
        driver.tap([(tap_x, tap_y)])
    elif "xpath" in data:
        element = driver.find_element(AppiumBy.XPATH, data["xpath"])
        element.click()


def process_web_input(data, driver):
    """Process web input action"""
    logging.info("Web input: %s", data)
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


def process_mobile_input(data, driver):
    """Process mobile input action"""
    logging.info("Mobile input: %s", data)
    if "bounds" in data:
        bounds = data["bounds"]
        left, top, right, bottom = parse_bounds(bounds)
        tap_x = left + (right - left) / 2
        tap_y = top + (bottom - top) / 2
        driver.tap([(tap_x, tap_y)])
        element = driver.find_element(AppiumBy.XPATH, "//*[@focused='true']")
        element.send_keys(data["value"])
        try:
            driver.hide_keyboard()
        except:
            pass
    elif "xpath" in data:
        element = driver.find_element(AppiumBy.XPATH, data["xpath"])
        element.click()
        element = driver.find_element(AppiumBy.XPATH, "//*[@focused='true']")
        element.send_keys(data["value"])
        try:
            driver.hide_keyboard()
        except:
            pass


def process_web_scroll(data, driver):
    """Process web scroll action"""
    logging.info("Web scroll: %s", data)
    scroll_x = data.get("swipe_end_x", 0) - data.get("swipe_start_x", 0)
    scroll_y = data.get("swipe_end_y", 0) - data.get("swipe_start_y", 0)
    driver.execute_script(f"window.scrollBy({scroll_x}, {scroll_y});")


def process_mobile_swipe(data, driver):
    """Process mobile swipe action"""
    logging.info("Mobile swipe: %s", data)
    swipe_start_x = data["swipe_start_x"]
    swipe_start_y = data["swipe_start_y"]
    swipe_end_x = data["swipe_end_x"]
    swipe_end_y = data["swipe_end_y"]
    duration = data.get("duration", 500)
    driver.swipe(
        swipe_start_x, swipe_start_y, swipe_end_x, swipe_end_y, duration
    )
    sleep(duration / 1000)


def get_current_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S")


def keep_driver_live(driver, platform):
    """Keep driver alive based on platform"""
    try:
        while driver:
            if platform == "web":
                driver.current_url
            else:
                driver.page_source
            sleep(10)
    except Exception as e:
        logging.info("Closing keep-alive thread: %s", e)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Universal AI Testing Tool")
    parser.add_argument("prompt", help="Prompt file")
    parser.add_argument("task", help="Task file")
    parser.add_argument("config", help="Platform configuration file")
    parser.add_argument(
        "--appium", default="localhost:4723", help="Appium server (for mobile)"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode"
    )
    parser.add_argument("--reports", default="./reports", help="Reports folder")

    args = parser.parse_args()

    prompt = read_file_content(args.prompt)
    tasks = json.loads(read_file_content(args.task))
    platform_config = json.loads(read_file_content(args.config))

    # Create driver based on platform
    driver = create_driver(args.appium, platform_config)
    platform = platform_config.get("platform", "").lower()

    # For web, navigate to initial URL
    if platform == "web" and "url" in platform_config:
        logging.info("Navigating to URL: %s", platform_config["url"])
        driver.get(platform_config["url"])

    driver.implicitly_wait(0.2)
    thread = threading.Thread(target=lambda: keep_driver_live(driver, platform))
    thread.start()
    logging.info("Keep-alive thread started")

    for task in tasks:
        logging.info("Processing task: %s", task)
        name = task["task"]
        details = task["details"]
        skip = task.get("skip", False)

        if skip:
            logging.info("Skipping %s", name)
            continue

        task_folder = create_folder(
            f"{args.reports}/{name}/{get_current_timestamp()}"
        )
        write_to_file(f"{task_folder}/task.json", json.dumps(task))
        write_to_file(f"{task_folder}/config.json", json.dumps(platform_config))

        sleep(1)

        # Detect platform from page source
        initial_source = driver.page_source
        detected_platform = PlatformDetector.detect_platform(initial_source)
        logging.info("Detected platform: %s", detected_platform)

        page_source_file = take_page_source(
            driver, task_folder, "step_0", detected_platform
        )
        screenshot_file = take_screenshot(
            driver, task_folder, "step_0", detected_platform
        )

        history_actions = []
        step = 0

        while (
            page_source_file is not None and step < 50
        ):  # Prevent infinite loops
            step += 1

            if args.debug:
                next_action = input("Next action: ")
            else:
                next_action = generate_next_action(
                    prompt,
                    details,
                    history_actions,
                    page_source_file,
                    screenshot_file,
                    detected_platform,
                )

            logging.info("Step %s: %s", step, next_action)

            page_source_file, screenshot_file, action_result = (
                process_next_action(
                    next_action,
                    driver,
                    task_folder,
                    f"step_{step}",
                    detected_platform,
                )
            )

            write_to_file(f"{task_folder}/step_{step}.json", action_result)
            history_actions.append(action_result)

            # Check if task is finished
            result_data = json.loads(action_result)
            if result_data["action"] in ["finish", "error"]:
                break

    try:
        driver.quit()
    except Exception:
        logging.exception("Error quitting driver")
