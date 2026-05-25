import discord
import asyncio
from src.utils import parse_hex_color

class ServerTemplateEngine:
    def __init__(self, guild: discord.Guild, template_data: dict = None, progress_dm: discord.Message = None):
        self.guild = guild
        self.data = template_data or {}
        self.progress_dm = progress_dm
        self.rate_limit_buffer = 1.2
        
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
        
        filled_blocks = int(percentage / 10)
        empty_blocks = 10 - filled_blocks
        progress_bar_string = "█" * filled_blocks + "░" * empty_blocks

        embed = discord.Embed(
            title="⚙️ Setting Up Your Server...",
            description=f"Currently building the template layout for **{self.guild.name}**.",
            color=discord.Color.blue()
        )
        embed.add_field(
            name="Overall Progress", 
            value=f"`{progress_bar_string}` **{percentage}%**", 
            inline=False
        )
        embed.add_field(
            name="What I'm doing right now", 
            value=f"✨ *{current_action}*", 
            inline=False
        )
        embed.set_footer(text=f"Item {self.current_operation_count} out of {self.total_operations} created")
        
        try:
            await self.progress_dm.edit(content=None, embed=embed)
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
            await self.update_progress_bar(f"Creating the role: '{role_name}'")
            
            await self.guild.create_role(
                name=role_name,
                color=parse_hex_color(role_info.get("color", "#FFFFFF")),
                hoist=role_info.get("hoist", False),
                reason="Applying server template"
            )
            await asyncio.sleep(self.rate_limit_buffer)

    async def build_channels(self):
        for cat_info in self.data.get("categories", []):
            cat_name = cat_info.get("name")
            await self.update_progress_bar(f"Creating the category folder: '{cat_name}'")
            
            category = await self.guild.create_category(name=cat_name)
            await asyncio.sleep(self.rate_limit_buffer)

            for chan_info in cat_info.get("channels", []):
                name = chan_info.get("name")
                chan_type = chan_info.get("type", "text")
                await self.update_progress_bar(f"Creating the channel: #{name}")

                if chan_type == "text":
                    created_channel = await self.guild.create_text_channel(
                        name=name, 
                        category=category, 
                        topic=chan_info.get("topic")
                    )
                    
                    # Feature 5 retained intact
                    for msg in chan_info.get("messages", []):
                        embed = discord.Embed(
                            title=msg.get("title", ""),
                            description=msg.get("description", ""),
                            color=parse_hex_color(msg.get("color", "#FFFFFF"))
                        )
                        await created_channel.send(embed=embed)
                        await asyncio.sleep(0.5)

                elif chan_type == "voice":
                    await self.guild.create_voice_channel(
                        name=name, 
                        category=category
                    )
                await asyncio.sleep(self.rate_limit_buffer)

    async def execute_full_deployment(self, wipe_first: bool = False):
        if wipe_first:
            await self.purge_current_guild()
        await self.build_roles()
        await self.build_channels()

    # Feature 3 retained intact
    def generate_backup_template(self) -> dict:
        backup = {"roles": [], "categories": []}
        for role in self.guild.roles:
            if not role.is_default() and not role.managed:
                backup["roles"].append({
                    "name": role.name,
                    "color": f"#{role.color.value:06x}",
                    "hoist": role.hoist
                })
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