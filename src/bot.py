import io
import json
import os
import time
from typing import Optional

import discord
from discord import app_commands
from dotenv import load_dotenv

from src.core_engine import ServerTemplateEngine
from src.utils import (
    fetch_available_templates,
    fetch_remote_json,
    parse_json_string,
    validate_template_data,
)
from src.views import DeploymentConfirmationView, TemplateModalLauncherView, WizardSetupView

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

    async def refresh_template_cache(self) -> list[str]:
        current_time = time.time()
        if not self.template_cache or (current_time - self.last_cache_update) > self.cache_duration:
            try:
                fetched = await fetch_available_templates(OWNER, REPO)
                if fetched:
                    self.template_cache = fetched
                    self.last_cache_update = current_time
            except Exception as exc:
                print(f"[Warning] Cache fetch error: {exc}")
        return self.template_cache

    async def setup_hook(self):
        await self.tree.sync()


bot = TemplateBot()


async def template_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    cache = await bot.refresh_template_cache()
    return [app_commands.Choice(name=t, value=t) for t in cache if current.lower() in t.lower()][:25]


def compact_error_list(errors: list[str], limit: int = 8) -> str:
    shown = errors[:limit]
    lines = [f"• {item}" for item in shown]
    if len(errors) > limit:
        lines.append(f"• ...and {len(errors) - limit} more issue(s).")
    return "\n".join(lines)


async def load_json_from_attachment(attachment: discord.Attachment) -> tuple[Optional[dict], Optional[str]]:
    if not attachment.filename.lower().endswith(".json"):
        return None, "The uploaded file must end with `.json`."

    if attachment.size > 1_000_000:
        return None, "The uploaded JSON file is too large. Please keep it under 1 MB."

    try:
        payload = await attachment.read()
    except discord.HTTPException:
        return None, "I couldn't download the uploaded file from Discord."

    try:
        raw_text = payload.decode("utf-8")
    except UnicodeDecodeError:
        return None, "The uploaded file must be UTF-8 encoded JSON."

    return parse_json_string(raw_text)


async def resolve_deploy_template_source(
    template_id: Optional[str],
    template_file: Optional[discord.Attachment],
    json_payload: Optional[str],
) -> tuple[Optional[str], Optional[dict], Optional[str]]:
    provided_sources = [
        bool(template_id and template_id.strip()),
        template_file is not None,
        bool(json_payload and json_payload.strip()),
    ]

    if sum(provided_sources) == 0:
        return None, None, "Provide one source: a GitHub template name, an uploaded `.json` file, or pasted JSON text."

    if sum(provided_sources) > 1:
        return None, None, "Please provide only one source at a time: GitHub template, uploaded file, or pasted JSON."

    if template_id and template_id.strip():
        normalized_template_id = template_id.strip()
        raw_github_url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/templates/{normalized_template_id}.json"
        json_data = await fetch_remote_json(raw_github_url)
        if not json_data:
            return None, None, f"I couldn't find or download the GitHub template `{normalized_template_id}`."
        return normalized_template_id, json_data, None

    if template_file is not None:
        json_data, error = await load_json_from_attachment(template_file)
        if error:
            return None, None, error
        return template_file.filename, json_data, None

    json_data, error = parse_json_string(json_payload or "")
    if error:
        return None, None, error
    return "pasted-json", json_data, None


async def run_deployment_pipeline(
    interaction: discord.Interaction,
    template_label: str,
    json_data: dict,
    community_name: str,
    confirmation_msg: discord.Message,
    view: DeploymentConfirmationView,
):
    wipe_selected = view.action_choice == "wipe"
    if wipe_selected:
        await confirmation_msg.edit(content="Cleaning out old channels and roles now...", embed=None, view=None)
    else:
        await confirmation_msg.edit(content="Starting setup. Adding new channels and roles alongside existing ones...", embed=None, view=None)

    tracking_dm_msg = None
    try:
        init_embed = discord.Embed(
            title="Setting Up Your Server",
            description=f"Currently building the template layout for **{interaction.guild.name}**.",
            color=discord.Color.blue(),
        )
        init_embed.add_field(name="Overall Progress", value="`..........` **0%**", inline=False)
        init_embed.add_field(name="What I'm doing right now", value="Starting setup process...", inline=False)
        tracking_dm_msg = await interaction.user.send(embed=init_embed)
    except discord.Forbidden:
        print(f"[Notice] DMs are closed for {interaction.user.name}.")

    try:
        engine = ServerTemplateEngine(
            guild=interaction.guild,
            template_data=json_data,
            progress_dm=tracking_dm_msg,
            placeholders={"community_name": community_name},
        )
        await engine.execute_full_deployment(wipe_first=wipe_selected)

        try:
            success_embed = discord.Embed(
                title="Deployment Complete",
                description=f"The `{template_label}` template has been successfully built on your server.",
                color=discord.Color.green(),
            )
            success_embed.add_field(name="Server Name", value=interaction.guild.name, inline=True)
            success_embed.add_field(name="Community Name", value=str(community_name), inline=True)
            await interaction.user.send(embed=success_embed)
        except discord.Forbidden:
            pass

        await confirmation_msg.edit(content="Success. Your new layout configuration is ready to go.", embed=None, view=None)
    except Exception as exc:
        try:
            await confirmation_msg.edit(content=f"Setup stopped due to an error: `{exc}`", embed=None, view=None)
        except discord.NotFound:
            pass


async def start_deploy_confirmation(
    interaction: discord.Interaction,
    source_label: str,
    json_data: dict,
):
    validation_errors = validate_template_data(json_data)
    if validation_errors:
        await interaction.followup.send(
            "The template JSON is not valid for deployment.\n"
            f"{compact_error_list(validation_errors)}"
        )
        return

    async def modal_submit_callback(modal_interaction: discord.Interaction, community_prefix: str):
        embed = discord.Embed(
            title="Double-Check Before Deploying",
            description=(
                f"Template source: `{source_label}`\n"
                f"Community name override: **{community_prefix}**"
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(
            name="Warning",
            value="Choosing **Wipe & Deploy** completely removes the current server layout first.",
            inline=False,
        )
        confirm_view = DeploymentConfirmationView(owner_id=interaction.guild.owner_id)
        msg = await modal_interaction.followup.send(embed=embed, view=confirm_view)
        await confirm_view.wait()
        if confirm_view.action_choice == "cancel" or confirm_view.action_choice is None:
            await msg.edit(content="Cancelled. No changes were made to your server.", embed=None, view=None)
            return
        await run_deployment_pipeline(modal_interaction, source_label, json_data, community_prefix, msg, confirm_view)

    launcher_view = TemplateModalLauncherView(owner_id=interaction.guild.owner_id, callback_func=modal_submit_callback)
    await interaction.followup.send(
        "Template loaded successfully. Open the setup form below to confirm placeholder values before deployment.",
        view=launcher_view,
    )


@bot.tree.command(name="deploy", description="Builds a new server layout from GitHub, an uploaded JSON file, or pasted JSON.")
@app_commands.describe(
    template_id="Existing template name from the GitHub /templates folder",
    template_file="Upload a custom .json template file",
    json_payload="Paste raw template JSON directly into the command",
)
async def deploy_template(
    interaction: discord.Interaction,
    template_id: Optional[str] = None,
    template_file: Optional[discord.Attachment] = None,
    json_payload: Optional[str] = None,
):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Access denied: only the Server Owner can run this command.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    source_label, json_data, error = await resolve_deploy_template_source(template_id, template_file, json_payload)
    if error:
        await interaction.followup.send(f"Error: {error}")
        return

    await start_deploy_confirmation(interaction, source_label or "template", json_data or {})


@bot.tree.command(name="setup", description="Launches the step-by-step interactive configuration wizard setup workflow.")
async def interactive_setup_wizard(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Access denied: only the Server Owner can launch the guided setup wizard.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=False)
    available_configs = await bot.refresh_template_cache()
    if not available_configs:
        await interaction.followup.send("Error: could not find any template profiles in the configured repository.")
        return

    wizard_view = WizardSetupView(owner_id=interaction.guild.owner_id, templates=available_configs)
    wizard_msg = await interaction.followup.send(
        "Welcome to the Server Setup Wizard.\nPlease choose a layout config file from the list below:",
        view=wizard_view,
    )
    await wizard_view.wait()

    if not wizard_view.selected_template:
        await wizard_msg.edit(content="Wizard closed: selection timed out or was cancelled.", view=None)
        return

    raw_github_url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/templates/{wizard_view.selected_template}.json"
    json_data = await fetch_remote_json(raw_github_url)
    if not json_data:
        await wizard_msg.edit(content="Error: I couldn't download the selected template from GitHub.", view=None)
        return

    async def wizard_modal_callback(modal_interaction: discord.Interaction, community_prefix: str):
        confirm_view = DeploymentConfirmationView(owner_id=interaction.guild.owner_id)
        embed = discord.Embed(
            title="Execution Path Confirmation",
            description=(
                f"Applying layout config: `{wizard_view.selected_template}`\n"
                f"Community name override: `{community_prefix}`"
            ),
            color=discord.Color.orange(),
        )
        msg = await modal_interaction.followup.send(embed=embed, view=confirm_view)
        await confirm_view.wait()
        if confirm_view.action_choice == "cancel" or confirm_view.action_choice is None:
            await msg.edit(content="Cancelled.", embed=None, view=None)
            return
        await run_deployment_pipeline(modal_interaction, wizard_view.selected_template, json_data, community_prefix, msg, confirm_view)

    launcher_view = TemplateModalLauncherView(owner_id=interaction.guild.owner_id, callback_func=wizard_modal_callback)
    await wizard_msg.edit(
        content=(
            f"Selected layout configuration profile: `{wizard_view.selected_template}`.\n"
            "Click below to configure placeholder values before deployment."
        ),
        view=launcher_view,
    )


@bot.tree.command(name="preview", description="Displays a text tree blueprint representation before initializing deployment.")
@app_commands.autocomplete(template_id=template_autocomplete)
async def preview_template_layout(interaction: discord.Interaction, template_id: str):
    await interaction.response.defer(ephemeral=True)
    raw_github_url = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/main/templates/{template_id}.json"
    json_data = await fetch_remote_json(raw_github_url)
    if not json_data:
        await interaction.followup.send("Error: could not load the requested template.")
        return

    validation_errors = validate_template_data(json_data)
    if validation_errors:
        await interaction.followup.send(
            "The selected template is not valid.\n"
            f"{compact_error_list(validation_errors)}"
        )
        return

    engine = ServerTemplateEngine(guild=interaction.guild, template_data=json_data, placeholders={"community_name": "Preview"})
    text_tree_diagram = engine.generate_layout_tree_preview(label=template_id)
    await interaction.followup.send(content=text_tree_diagram)


@bot.tree.command(name="backup", description="Saves your current server channels and roles into a backup template file.")
async def backup_server(interaction: discord.Interaction):
    if interaction.user.id != interaction.guild.owner_id:
        await interaction.response.send_message("Access denied: only the Server Owner can create backups.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)
    try:
        engine = ServerTemplateEngine(guild=interaction.guild)
        backup_dict = engine.generate_backup_template()
        json_string = json.dumps(backup_dict, indent=2)
        file_stream = io.BytesIO(json_string.encode("utf-8"))
        discord_file = discord.File(fp=file_stream, filename=f"backup_{interaction.guild.id}.json")
        await interaction.followup.send(
            content="Backup created. You can upload this file later or place it in your GitHub `/templates` folder.",
            file=discord_file,
        )
    except Exception as exc:
        await interaction.followup.send(f"Sorry, I ran into an error while saving your layout: `{exc}`")


@deploy_template.autocomplete("template_id")
async def auto_complete_wrapper(interaction: discord.Interaction, current: str):
    return await template_autocomplete(interaction, current)


@bot.event
async def on_ready():
    print(f"Bot is online and logged in as {bot.user}")


if __name__ == "__main__":
    bot.run(os.getenv("DISCORD_TOKEN"))
