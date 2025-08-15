import argparse
import datetime
import json
import os
import threading
from time import sleep
from PIL import Image
import xml.etree.ElementTree as ET
import yaml

from src.utils.driver_utils import create_driver, keep_driver_live
from src.modules.llm_client import generate_next_action, read_file_content
from src.modules.actions import process_next_action


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


def create_folder(folder_path):
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path


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
        return f"{folder}/{name}.yaml"
    else:
        # Mobile platforms
        write_to_file(f"{folder}/{name}.xml", driver.page_source)
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
    return f"{folder}/{name}.jpg"


def get_current_timestamp():
    now = datetime.datetime.now()
    return now.strftime("%Y-%m-%d-%H-%M-%S")


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
        driver.get(platform_config["url"])

    driver.implicitly_wait(0.2)
    thread = threading.Thread(target=lambda: keep_driver_live(driver, platform))
    thread.start()

    for task in tasks:
        print(f"Processing task: {task}")
        name = task["task"]
        details = task["details"]
        skip = task.get("skip", False)

        if skip:
            print(f"Skipping {name}")
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
        print(f"Detected platform: {detected_platform}")

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

            print(f"Step {step}: {next_action}")

            page_source_file, screenshot_file, action_result = (
                process_next_action(
                    next_action,
                    driver,
                    task_folder,
                    f"step_{step}",
                    detected_platform,
                    take_page_source,
                    take_screenshot,
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
    except:
        pass
