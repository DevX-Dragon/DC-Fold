import discord
import aiohttp
import json
from typing import Any, List, Optional

def parse_hex_color(hex_str: str) -> discord.Color:
    """" " "  Safely converts a hex string into a discord.Color object.
    Handles formats with or without the leading '#' symbol.
    """
    if not hex_str:
        return discord.Color.default()
        
    try:
        # Strip out the '#' if the user added it in the JSON file
        clean_hex = hex_str.lstrip('#')
        # Convert hex string to a base-16 integer
        return discord.Color(int(clean_hex, 16))
    except ValueError:
        # If someone typed invalid hex (like "G12345"), fall back gracefully
        print(f"[Warning] Invalid hex color format provided: '{hex_str}'. Using default color.")
        return discord.Color.default()


async def fetch_remote_json(url: str) -> Optional[dict]:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    # Pass content_type=None to bypass the strict mimetype verification check
                    return await response.json(content_type=None)
                print(f"[Error] Failed to fetch raw file. HTTP Status: {response.status}")
                return None
        except Exception as e:
            print(f"[Error] Exception occurred while downloading JSON: {e}")
            return None


async def fetch_available_templates(owner: str, repo: str) -> List[str]:
    """
" " "  Queries the GitHub API to list all .json files inside the /templates directory.
    Returns a list of strings representing the clean template IDs (filenames minus .json).
    """
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/templates"
    
    # GitHub API requests require an explicit user-agent header or appropriate format headers
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Discord-Template-Bot-Engine"
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    print(f"[Error] GitHub API returned status code: {response.status}")
                    return []
                
                contents = await response.json()
                
                # We iterate through the directory items, making sure they are files and end with .json
                template_ids = []
                for item in contents:
                    if item.get("type") == "file" and item.get("name", "").endswith(".json"):
                        # Drop the ".json" extension to treat the clean filename as the user's template_id
                        clean_id = item["name"].replace(".json", "")
                        template_ids.append(clean_id)
                        
                return template_ids
                
        except Exception as e:
            print(f"[Error] Exception occurred while fetching GitHub directory contents: {e}")
            return []


def parse_json_string(raw_text: str) -> tuple[Optional[dict], Optional[str]]:
    if not raw_text or not raw_text.strip():
        return None, "The JSON input was empty."

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON near line {exc.lineno}, column {exc.colno}: {exc.msg}"

    if not isinstance(parsed, dict):
        return None, "The template JSON must be a top-level object."

    return parsed, None


def validate_template_data(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    roles = data.get("roles")
    categories = data.get("categories")

    if roles is None or not isinstance(roles, list):
        errors.append("`roles` must be a list.")
    if categories is None or not isinstance(categories, list):
        errors.append("`categories` must be a list.")

    if errors:
        return errors

    for index, role in enumerate(roles, start=1):
        if not isinstance(role, dict):
            errors.append(f"`roles[{index}]` must be an object.")
            continue
        if not role.get("name"):
            errors.append(f"`roles[{index}].name` is required.")
        permissions = role.get("permissions", [])
        if permissions is not None and not isinstance(permissions, list):
            errors.append(f"`roles[{index}].permissions` must be a list when provided.")

    for cat_index, category in enumerate(categories, start=1):
        if not isinstance(category, dict):
            errors.append(f"`categories[{cat_index}]` must be an object.")
            continue
        if not category.get("name"):
            errors.append(f"`categories[{cat_index}].name` is required.")

        channels = category.get("channels")
        if not isinstance(channels, list):
            errors.append(f"`categories[{cat_index}].channels` must be a list.")
            continue

        for channel_index, channel in enumerate(channels, start=1):
            if not isinstance(channel, dict):
                errors.append(f"`categories[{cat_index}].channels[{channel_index}]` must be an object.")
                continue

            if not channel.get("name"):
                errors.append(f"`categories[{cat_index}].channels[{channel_index}].name` is required.")

            channel_type = channel.get("type", "text")
            if channel_type not in {"text", "voice"}:
                errors.append(
                    f"`categories[{cat_index}].channels[{channel_index}].type` must be `text` or `voice`."
                )

            slowmode = channel.get("slowmode", 0)
            if not isinstance(slowmode, int) or slowmode < 0:
                errors.append(
                    f"`categories[{cat_index}].channels[{channel_index}].slowmode` must be a non-negative integer."
                )

            messages = channel.get("messages", [])
            if messages is not None and not isinstance(messages, list):
                errors.append(
                    f"`categories[{cat_index}].channels[{channel_index}].messages` must be a list when provided."
                )

    return errors
