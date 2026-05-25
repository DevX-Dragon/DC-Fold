import discord
import aiohttp
from typing import List, Optional

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