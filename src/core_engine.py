import discord
import asyncio
import json
from src.utils import parse_hex_color

class ServerTemplateEngine:
    def __init__(self, guild: discord.Guild, template_data: dict = None, progress_dm: discord.Message = None, placeholders: dict = None):
        self.guild = guild
        self.progress_dm = progress_dm
        self.placeholders = placeholders or {}
        self.rate_limit_buffer = 1.2
        
        target_dict = template_data if isinstance(template_data, dict) else {}
        template_variables = {
            key: value
            for key, value in target_dict.get("variables", {}).items()
            if isinstance(value, (str, int, float, bool))
        }
        merged_placeholders = {**template_variables, **self.placeholders}
        raw_json_str = json.dumps(target_dict)
        
        for key, val in merged_placeholders.items():
            raw_json_str = raw_json_str.replace(f"{{{{{key}}}}}", str(val))
            
        self.data = json.loads(raw_json_str)
        self.total_roles = len(self.data.get("roles", []))
        self.total_categories = len(self.data.get("categories", []))
        self.total_channels = sum(len(cat.get("channels", [])) for cat in self.data.get("categories", []))
        self.total_operations = self.total_roles + self.total_categories + self.total_channels
        self.current_operation_count = 0

    async def update_progress_bar(self, current_action: str):
        if not self.progress_dm or self.total_operations == 0:
            return
        self.current_operation_count += 1
        percentage = min(int((self.current_operation_count / self.total_operations) * 100), 100)
        progress_bar_string = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
        embed = discord.Embed(title="⚙️ Setting Up Your Server...", description=f"Currently building the template layout for **{self.guild.name}**.", color=discord.Color.blue())
        embed.add_field(name="Overall Progress", value=f"`{progress_bar_string}` **{percentage}%**", inline=False)
        embed.add_field(name="What I'm doing right now", value=f"✨ *{current_action}*", inline=False)
        embed.set_footer(text=f"Item {self.current_operation_count} out of {self.total_operations} created")
        try:
            await self.progress_dm.edit(embed=embed)
        except discord.HTTPException:
            pass

    async def purge_current_guild(self):
        for channel in list(self.guild.channels):
            try:
                await channel.delete()
                await asyncio.sleep(0.3)
            except discord.HTTPException:
                pass
        for role in list(self.guild.roles):
            if not role.is_default() and not role.managed:
                try:
                    await role.delete()
                    await asyncio.sleep(0.3)
                except discord.HTTPException:
                    pass

    async def build_roles(self):
        for role_info in self.data.get("roles", []):
            role_name = role_info.get("name")
            
            existing_role = discord.utils.get(self.guild.roles, name=role_name)
            if existing_role:
                await self.update_progress_bar(f"Skipping role (Already Exists): '{role_name}'")
                continue
                
            await self.update_progress_bar(f"Creating the role: '{role_name}'")
            perms_to_add = discord.Permissions.none()
            for perm_name in role_info.get("permissions", []):
                if hasattr(perms_to_add, perm_name):
                    setattr(perms_to_add, perm_name, True)

            await self.guild.create_role(name=role_name, color=parse_hex_color(role_info.get("color", "#FFFFFF")), hoist=role_info.get("hoist", False), permissions=perms_to_add, reason="Applying server template")
            await asyncio.sleep(self.rate_limit_buffer)

    async def get_explicit_overwrites(self, requires_staff: bool) -> dict:
        if not requires_staff:
            return {}

        overwrites = {self.guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        for role in self.guild.roles:
            role_lower = role.name.lower()
            if any(k in role_lower for k in ["admin", "mod", "staff", "owner", "management"]):
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
        return overwrites

    async def build_channels(self):
        for cat_info in self.data.get("categories", []):
            cat_name = cat_info.get("name")
            
            category = discord.utils.get(self.guild.categories, name=cat_name)
            if not category:
                await self.update_progress_bar(f"Creating the category folder: '{cat_name}'")
                category = await self.guild.create_category(name=cat_name)
                await asyncio.sleep(self.rate_limit_buffer)
            else:
                await self.update_progress_bar(f"Using existing category folder: '{cat_name}'")

            for chan_info in cat_info.get("channels", []):
                name = chan_info.get("name")
                chan_type = chan_info.get("type", "text")
                requires_staff = chan_info.get("requires_staff", False)
                slowmode_delay = chan_info.get("slowmode", 0)
                
                existing_channel = discord.utils.get(category.channels, name=name)
                if existing_channel:
                    await self.update_progress_bar(f"Skipping channel (Already Exists): #{name}")
                    continue

                await self.update_progress_bar(f"Creating the channel: #{name}")
                permission_overwrites = await self.get_explicit_overwrites(requires_staff)

                if chan_type == "text":
                    created_channel = await self.guild.create_text_channel(name=name, category=category, topic=chan_info.get("topic"), overwrites=permission_overwrites, slowmode_delay=slowmode_delay)
                    for msg in chan_info.get("messages", []):
                        embed = discord.Embed(title=msg.get("title", ""), description=msg.get("description", ""), color=parse_hex_color(msg.get("color", "#FFFFFF")))
                        await created_channel.send(embed=embed)
                        await asyncio.sleep(0.5)
                elif chan_type == "voice":
                    await self.guild.create_voice_channel(name=name, category=category, overwrites=permission_overwrites)
                await asyncio.sleep(self.rate_limit_buffer)

    async def execute_full_deployment(self, wipe_first: bool = False):
        if wipe_first:
            await self.purge_current_guild()
        await self.build_roles()
        await self.build_channels()

    def generate_layout_tree_preview(self, label: str) -> str:
        lines = [f"📁 **Preview Structure Outline for: `{label}`**", f"\x60\x60\x60text", f" Guild: {self.guild.name}"]
        for role in self.data.get("roles", []):
            lines.append(f"  ├── [Role] {role.get('name')}")
        for cat in self.data.get("categories", []):
            lines.append(f"  └── 📂 {cat.get('name')}")
            for chan in cat.get("channels", []):
                sym = "📝" if chan.get("type") == "text" else "🔊"
                lines.append(f"      ├── {sym} {chan.get('name')}")
        lines.append(f"\x60\x60\x60")
        return "\n".join(lines)

    def generate_backup_template(self) -> dict:
        backup = {"roles": [], "categories": []}
        for role in self.guild.roles:
            if not role.is_default() and not role.managed:
                backup["roles"].append({"name": role.name, "color": f"#{role.color.value:06x}", "hoist": role.hoist})
        backup["roles"].reverse()
        for category in self.guild.categories:
            cat_data = {"name": category.name, "channels": []}
            for channel in category.channels:
                chan_type = "text" if isinstance(channel, discord.TextChannel) else "voice"
                chan_data = {"name": channel.name, "type": chan_type}
                if chan_type == "text" and channel.topic:
                    chan_data["topic"] = channel.topic
                cat_data["channels"].append(chan_data)
            backup["categories"].append(cat_data)
        return backup
