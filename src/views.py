import discord

class TemplatePlaceholderModal(discord.ui.Modal, title="Template Customization Options"):
    community_name = discord.ui.TextInput(label="Community Name Prefix", placeholder="e.g., Alpha, DevX, Gaming", required=True, max_length=15)

    def __init__(self, callback_func):
        super().__init__()
        self.callback_func = callback_func

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        await self.callback_func(interaction, self.community_name.value)


class TemplateModalLauncherView(discord.ui.View):
    def __init__(self, owner_id: int, callback_func, button_label: str = "Open Variables Setup Form"):
        super().__init__(timeout=120.0)
        self.owner_id = owner_id
        self.callback_func = callback_func
        self.open_modal.label = button_label

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the Server Owner can open the template setup form.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Open Variables Setup Form", style=discord.ButtonStyle.success)
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = TemplatePlaceholderModal(callback_func=self.callback_func)
        await interaction.response.send_modal(modal)

class DeploymentConfirmationView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=120.0)
        self.owner_id = owner_id
        self.action_choice = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the Server Owner can trigger deployment variables.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Wipe & Deploy", style=discord.ButtonStyle.danger, custom_id="confirm_wipe")
    async def confirm_wipe(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.action_choice = "wipe"
        self.stop()

    @discord.ui.button(label="Keep Existing & Deploy", style=discord.ButtonStyle.primary, custom_id="confirm_keep")
    async def confirm_keep(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.action_choice = "keep"
        self.stop()

    @discord.ui.button(label="Cancel Setup", style=discord.ButtonStyle.secondary, custom_id="cancel_deploy")
    async def cancel_deploy(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.action_choice = "cancel"
        self.stop()

class WizardTemplateDropdown(discord.ui.Select):
    def __init__(self, templates: list[str]):
        options = [discord.SelectOption(label=t, value=t) for t in templates[:25]]
        super().__init__(placeholder="Select a server template configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.selected_template = self.values[0]
        self.view.stop()
        await interaction.response.defer()

class WizardSetupView(discord.ui.View):
    def __init__(self, owner_id: int, templates: list[str]):
        super().__init__(timeout=60.0)
        self.owner_id = owner_id
        self.selected_template = None
        self.add_item(WizardTemplateDropdown(templates))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Only the Server Owner can use this configuration wizard.", ephemeral=True)
            return False
        return True
