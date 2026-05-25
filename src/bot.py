import os
import json
import io
import time
import discord
from discord import app_commands
from dotenv import load_dotenv
from src.utils import fetch_remote_json, fetch_available_templates
from src.core_engine import ServerTemplateEngine
from src.views import DeploymentConfirmationView

load_dotenv()
OWNER = os.getenv("GITHUB_OWNER")
REPO = os.getenv("GITHUB_REPO")

class TemplateBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)
        self.template_cache = []
        self.last_cache_update = 0
        self.cache_duration = 60

    async def setup_hook(self):
        await self.tree.sync()

bot = TemplateBot()

async def template_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    current_time = time.time()
    if not bot.template_cache or (current_time - bot.last_cache_update) > bot.cache_duration:
        try:
            fetched_templates = await fetch_available_templates(OWNER, REPO)
            if fetched_templates:
                bot.template_cache = fetched_templates
                bot.last_cache_update = current_time
        except Exception as e:
            print(f"[Warning] Failed to update autocomplete cache: {e}")

    return [
        app_commands.Choice(name=t_id, value=t_id)
        for t_id in bot.template_cache if current.lower() in t_id.lower()
    ][:25]

@bot.tree.command(name="deploy", description="Builds a new server layout using a template file from GitHub.")
async def deploy_template(interaction: discord.Interaction, template_id: str):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message(
            "❌ **Access Denied**: Only the actual Server Owner can use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    
    raw_github_url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/templates/{template_id}.json"
    json_data = await fetch_remote_json(raw_github_url)

    if not json_data:
        await interaction.followup.send("❌ Error: I couldn't find or download that template file from GitHub.")
        return

    role_count = len(json_data.get("roles", []))
    cat_count = len(json_data.get("categories", []))
    chan_count = sum(len(cat.get("channels", [])) for cat in json_data.get("categories", []))

    embed = discord.Embed(
        title="🛡️ Double-Check Before Deploying",
        description=f"You are about to load the template: `{template_id}`.\nPlease choose how you want to build this server below.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Roles to create", value=str(role_count), inline=True)
    embed.add_field(name="Categories to create", value=str(cat_count), inline=True)
    embed.add_field(name="Channels to create", value=str(chan_count), inline=True)
    embed.add_field(
        name="⚠️ Warning", 
        value="If you choose **Wipe & Deploy**, the bot will completely delete all channels and roles currently in this server. This cannot be undone!", 
        inline=False
    )

    view = DeploymentConfirmationView(owner_id=interaction.guild.owner_id)
    confirm_msg = await interaction.followup.send(embed=embed, view=view)

    await view.wait()

    if view.action_choice == "cancel" or view.action_choice is None:
        await confirm_msg.edit(content="❌ **Cancelled.** No changes were made to your server.", embed=None, view=None)
        return

    wipe_selected = (view.action_choice == "wipe")
    
    if wipe_selected:
        await confirm_msg.edit(content="💣 Cleaning out old channels and roles now...", embed=None, view=None)
    else:
        await confirm_msg.edit(content="🏗️ Starting setup! Adding new channels and roles alongside your existing ones...", embed=None, view=None)

    tracking_dm_msg = None
    try:
        init_embed = discord.Embed(
            title="⚙️ Setting Up Your Server...",
            description=f"Currently building the template layout for **{interaction.guild.name}**.",
            color=discord.Color.blue()
        )
        init_embed.add_field(name="Overall Progress", value="`░░░░░░░░░░` **0%**", inline=False)
        init_embed.add_field(name="What I'm doing right now", value="🛠️ *Starting setup process...*", inline=False)
        
        tracking_dm_msg = await interaction.user.send(embed=init_embed)
    except discord.Forbidden:
        print(f"[Notice] Could not DM {interaction.user.name} because their DMs are closed.")

    try:
        engine = ServerTemplateEngine(guild=interaction.guild, template_data=json_data, progress_dm=tracking_dm_msg)
        await engine.execute_full_deployment(wipe_first=wipe_selected)
        
        try:
            success_embed = discord.Embed(
                title="✅ All Done!",
                description=f"The `{template_id}` template has been successfully built on your server.",
                color=discord.Color.green()
            )
            success_embed.add_field(name="Server", value=interaction.guild.name, inline=True)
            success_embed.add_field(name="Roles Created", value=str(role_count), inline=True)
            success_embed.add_field(name="Channels Created", value=str(chan_count), inline=True)
            
            await interaction.user.send(embed=success_embed)
        except discord.Forbidden:
            pass

        if not wipe_selected:
            await confirm_msg.edit(content=f"✅ **Success!** Your new layout for `{template_id}` is ready to go.", embed=None, view=None)
            
    except Exception as e:
        try:
            err_embed = discord.Embed(title="❌ Something went wrong", description=f"An error stopped the setup: `{e}`", color=discord.Color.red())
            await interaction.user.send(embed=err_embed)
        except discord.Forbidden:
            pass
            
        try:
            await confirm_msg.edit(content=f"⚠️ Setup stopped due to an error: `{e}`", embed=None, view=None)
        except discord.NotFound:
            pass

@bot.tree.command(name="backup", description="Saves your current server channels and roles into a backup template file.")
async def backup_server(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message(
            "❌ **Access Denied**: Only the actual Server Owner can create backups.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    try:
        engine = ServerTemplateEngine(guild=interaction.guild)
        backup_dict = engine.generate_backup_template()

        json_string = json.dumps(backup_dict, indent=2)
        file_stream = io.BytesIO(json_string.encode("utf-8"))
        discord_file = discord.File(fp=file_stream, filename=f"backup_{interaction.guild.id}.json")

        await interaction.followup.send(
            content="📦 **Backup Created!** Here is your layout backup file. You can upload this straight into your GitHub repository's `/templates` folder to use it later.",
            file=discord_file
        )
    except Exception as e:
        await interaction.followup.send(f"⚠️ Sorry, I ran into an error while saving your layout: `{e}`")

@deploy_template.autocomplete('template_id')
async def auto_complete_wrapper(interaction: discord.Interaction, current: str):
    return await template_autocomplete(interaction, current)

@bot.event
async def on_ready():
    print(f"🚀 Bot is online and logged in as {bot.user}")

if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))