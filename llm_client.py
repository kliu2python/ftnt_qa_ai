"""Client for interacting with the language model service."""

from __future__ import annotations

from typing import List, Optional
import base64
import json
import requests


def read_file_content(file_path: str) -> Optional[str]:
    """Read and return the content of a file if it exists."""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' does not exist.")
    except IOError:
        print(f"Error: Unable to read the file '{file_path}'.")
    return None


def image_to_base64(image_path: str) -> str:
    """Convert an image file to a base64-encoded string."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def get_platform_specific_instructions(platform: str) -> str:
    """Return platform-specific instructions for the language model."""
    if platform == "ios":
        return (
            "- Use iOS element types: XCUIElementTypeButton, XCUIElementTypeTextField,"
            " etc.\n- Use @name, @label, @value attributes for identification\n"
            "- Calculate bounds from x, y, width, height attributes:"
            " [x,y][x+width,y+height]\n"
            "- Example XPath: //XCUIElementTypeButton[@name='Info'][@enabled='true']"
        )
    if platform == "android":
        return (
            "- Use Android element types and attributes\n"
            "- Use @text, @resource-id, @content-desc for identification\n"
            "- Use bounds attribute directly: bounds='[x1,y1][x2,y2]'\n"
            "- Example XPath: //*[@text='Settings'] or"
            " //*[@resource-id='com.app:id/button']"
        )
    if platform == "web":
        return (
            "- Use standard HTML elements: button, input, div, span, etc.\n"
            "- Use id, class, name, text content for identification\n"
            "- Use CSS selectors or XPath for web elements\n"
            "- Example XPath: //button[text()='Submit'] or //input[@id='username']\n"
            "- For bounds, use element.location and element.size from Selenium"
        )
    return "- Platform not recognized, use generic selectors"


def generate_next_action(
    prompt: str,
    task: str,
    history_actions: List[str],
    page_source_file: str,
    page_screenshot: str,
    platform: str,
) -> str:
    """Generate the next action by sending context to the LLM service."""
    screenshot_base64 = image_to_base64(page_screenshot)
    page_source = read_file_content(page_source_file) or ""
    history_actions_str = "\n".join(history_actions)

    platform_context = {
        "ios": "iOS XML with XCUIElementType elements",
        "android": "Android XML with android hierarchy",
        "web": "HTML DOM structure",
    }

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
        return result.get("response", "")
    except requests.exceptions.RequestException as err:
        print(f"Error calling Ollama API: {err}")
        return '{"action": "error", "reason": "API call failed"}'
    except json.JSONDecodeError as err:
        print(f"Error parsing Ollama response: {err}")
        return '{"action": "error", "reason": "Invalid JSON response"}'
